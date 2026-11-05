#!/usr/bin/env python3
"""Exercise a reviewed Flatpak app from installed code in a disposable desktop."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

import desktop_smoke as smoke


def prepare_store(store):
    """Explicit test-only Flathub bootstrap, never used by the product."""
    import gi
    gi.require_version('Flatpak','1.0')
    from gi.repository import Flatpak, Gio, GLib
    marker = store/'cozy-flatpak-fixture.json'
    identity = {'kind':'cozy-flatpak-test','uid':os.getuid()}
    if store.exists() and any(store.iterdir()):
        if not marker.is_file() or json.loads(marker.read_text())!=identity:
            raise RuntimeError('Refusing to configure a non-fixture Flatpak directory')
    store.mkdir(mode=0o700,parents=False,exist_ok=True)
    marker.write_text(json.dumps(identity)+'\n')
    installation = Flatpak.Installation.new_for_path(Gio.File.new_for_path(str(store)),True,None)
    try:
        remote = installation.get_remote_by_name('flathub',None)
    except GLib.Error:
        with urllib.request.urlopen('https://dl.flathub.org/repo/flathub.flatpakrepo',timeout=30) as stream:
            data = stream.read(65537)
        if len(data)>65536:
            raise RuntimeError('Repository descriptor exceeds the fixture limit')
        remote = Flatpak.Remote.new_from_file('flathub',GLib.Bytes.new(data))
        if remote.get_url()!='https://dl.flathub.org/repo/' or b'GPGKey=' not in data:
            raise RuntimeError('Unexpected Flathub fixture trust configuration')
        remote.set_gpg_verify(True)
        installation.add_remote(remote,True,None)


def instances(app_id):
    # Flatpak 1.14.6's Instance.get_all GI annotation is broken. The documented
    # machine-column CLI avoids its invalid GObject wrappers; no shell is used.
    text = subprocess.check_output(['flatpak', 'ps', '--columns=instance,pid,child-pid,application'], text=True, timeout=5)
    result = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) == 4 and fields[3] == app_id and all(re.fullmatch(r'\d+', value) for value in fields[:3]):
            result.append({'instance': fields[0], 'pid': int(fields[1]), 'childPid': int(fields[2])})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--desktop', choices=('kde','gnome','xfce'), required=True)
    parser.add_argument('--session', choices=('wayland','x11'), required=True)
    parser.add_argument('--browser', required=True)
    parser.add_argument('--launch-mode', choices=('kiosk','fullscreen'), required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--flatpak-user-dir', type=Path, required=True, help='Existing disposable Flatpak installation, outside the normal user home')
    parser.add_argument('--prepare-store', action='store_true', help='Explicitly create a new disposable Flathub test store first')
    parser.add_argument('--observe-seconds', type=int, default=0, choices=range(31), help='Pause for a VM screenshot before clicking close')
    args = parser.parse_args()
    if os.geteuid() == 0 or smoke.environment_errors(args.desktop,args.session):
        raise RuntimeError('Use an ordinary disposable user in the requested graphical session')
    store = args.flatpak_user_dir.resolve()
    if store.parent!=Path('/var/tmp') or not re.fullmatch(r'cozy-flatpak-[A-Za-z0-9-]+',store.name):
        raise RuntimeError('Expected a disposable /var/tmp/cozy-flatpak-* store')
    os.environ['FLATPAK_USER_DIR'] = str(store)
    if args.prepare_store:
        prepare_store(store)
    if not (store/'repo').is_dir():
        raise RuntimeError('Prepare the disposable store first or use --prepare-store')
    runtime = Path('/usr/share/cozy-kids-launcher')
    sys.path.insert(0,str(runtime))
    smoke.RUNTIME_SOURCE_ROOT = runtime
    from flatpak_catalog import recipe
    from process_supervisor import owned_processes
    value = recipe('tuxpaint')
    args.artifacts.mkdir(parents=True,exist_ok=True)
    report = {'desktop':args.desktop,'session':args.session,'browser':args.browser,'mode':args.launch_mode,
              'flatpak':subprocess.check_output(['flatpak','--version'],text=True).strip(),
              'checks':[], 'manualPending':['Physical drawing/keyboard/touch input', 'Final compositor focus and visual acceptance']}
    command = ['/usr/bin/cozy-kids-launcher','--browser',args.browser,'--launch-mode',args.launch_mode]
    launcher = None
    with tempfile.TemporaryDirectory(prefix='cozy-flatpak-desktop-',dir=smoke.temporary_home_parent(args.browser)) as directory:
        home = Path(directory)
        environment = {**os.environ,'HOME':directory,'COZY_KIDS_PORT':str(smoke.available_port()),'NO_PROXY':'127.0.0.1,localhost'}
        cache = home/'.cache/cozy-kids-launcher'
        base = 'http://127.0.0.1:'+environment['COZY_KIDS_PORT']
        def api(path, body=None):
            payload = None if body is None else json.dumps(body).encode()
            request = urllib.request.Request(base+path,data=payload,headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(request,timeout=45) as response:
                data = response.read()
                return json.loads(data) if data else None
        try:
            subprocess.run([*command,'--initialize-only'],env=environment,check=True)
            config = home/'.config/cozy-kids-launcher/config.json'
            entry = next(item for item in json.loads((runtime/'recommendations.json').read_text()) if item['id']=='tuxpaint')
            smoke.write_smoke_config(config,args.browser,entry)
            with (args.artifacts/'launcher.log').open('w') as log:
                launcher = subprocess.Popen(command,env=environment,stdout=log,stderr=log)
            smoke.wait_until(lambda: smoke._server_ready(base,launcher),timeout=45)
            before = subprocess.check_output(['flatpak','list','--user','--columns=ref,origin,active'],text=True,timeout=10)
            api('/api/packages/prepare',{'appId':'tuxpaint','source':'flatpak'})
            def settled():
                job = api('/api/packages/status')
                return job if job['status'] not in ('checking','installing') else None
            job = smoke.wait_until(settled,timeout=100)
            if job['status']=='ready':
                after = subprocess.check_output(['flatpak','list','--user','--columns=ref,origin,active'],text=True,timeout=10)
                assert before==after, 'Preparing a review changed installed refs'
                report['checks'].append('review leaves every installed app/runtime ref unchanged')
                assert job['source']=='flatpak' and job['flatpak']['scope']=='user'
                assert not instances(value['id'])
                try:
                    api('/api/packages/install',{'jobId':job['jobId'],'confirmationToken':'invalid'})
                    raise AssertionError('Forged consent was accepted')
                except urllib.error.HTTPError as error:
                    assert error.code==409
                api('/api/packages/install',{'jobId':job['jobId'],'confirmationToken':job['confirmationToken']})
                job = smoke.wait_until(settled,timeout=600)
                report['checks'].append('real Flatpak review, forged-token refusal, explicit consent and exact installed-ref verification')
            assert job['status']=='complete', job
            rec = next(item for item in api('/api/recommendations') if item['id']=='tuxpaint')
            assert rec['cmd']==entry['cmd'] and rec['flatpakRoute']['installed'] is True
            data = json.loads(config.read_text())
            data['profiles'][0]['tiles'][0]['cmd'] = rec['flatpakRoute']['cmd']
            assert api('/api/save-config',data)['status']=='ok'
            api('/launch/desktop-smoke',{})
            tile = smoke.wait_until(lambda: smoke.live_process_record(cache/'tile-process.pid','tile-process'))
            def owned_instance():
                pids = set(owned_processes(tile['pid']))
                return next((item for item in instances(value['id']) if item['pid'] in pids and item['childPid'] in pids), None)
            report['instance'] = smoke.wait_until(owned_instance,timeout=25)
            report['checks'].append('Flatpak app and sandbox belong to the tile supervisor tree')
            smoke.wait_until(lambda: record if (record:=smoke.live_process_record(cache/'overlay.pid','overlay')) and record.get('ready') is True else None)
            windows = smoke.wait_until(lambda: smoke.x11_window_ids('App Overlay'))
            (args.artifacts/'app-visible').touch()
            if args.observe_seconds:
                time.sleep(args.observe_seconds)
            smoke.x11_click_overlay_close(windows[-1])
            smoke.wait_until(lambda: not instances(value['id']),timeout=20)
            smoke.wait_until(lambda: not smoke.live_process_record(cache/'tile-process.pid','tile-process'),timeout=20)
            report['checks'].append('real overlay click closes the app, sandbox and owned process record')
            api('/exit-kids',{})
            launcher.wait(timeout=30)
            assert launcher.returncode==0
            report['checks'].append('Parent exit and launcher cleanup')
            report['outcome']='automation-passed-manual-pending'
        except Exception:
            report['outcome']='failed'
            raise
        finally:
            if launcher and launcher.poll() is None:
                launcher.terminate()
                launcher.wait(timeout=30)
            smoke.copy_runtime_artifacts(home,args.artifacts)
            (args.artifacts/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    main()

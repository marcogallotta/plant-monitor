#!/usr/bin/env python3
"""
Receive photos via Bluetooth OBEX Push and upload to plant-monitoring.

Setup (once):
  make bt-install
  bluetoothctl  →  power on / agent on / default-agent / discoverable on / pairable on
                →  pair from Android, then: trust <MAC>

Run:
  make bt-receive   (no sudo needed)

Env vars:
  BACKEND_URL        defaults to http://localhost:8001
  DASHBOARD_PASSWORD read from .env automatically, or set explicitly
"""
import os
import time
import requests
from pathlib import Path

# load .env from repo root so DASHBOARD_PASSWORD is available
_env = Path(__file__).parent.parent / '.env'
if _env.exists():
    for line in _env.read_text().splitlines():
        if '=' in line and not line.startswith('#'):
            k, _, v = line.partition('=')
            os.environ.setdefault(k.strip(), v.strip())

try:
    import dbus
    import dbus.service
    import dbus.mainloop.glib
    from gi.repository import GLib
except ImportError:
    raise SystemExit('Run: make bt-install')

BACKEND  = os.environ.get('BACKEND_URL', 'http://localhost:8001') + '/manual-photos'
PASSWORD = os.environ.get('DASHBOARD_PASSWORD', '')
AUTH     = ('user', PASSWORD) if PASSWORD else None

AGENT_PATH = '/plant/obex/agent'
STAGING    = Path.home() / 'plant-obex-inbox'
UPLOADED   = STAGING / 'uploaded'
FAILED     = STAGING / 'failed'
for d in (STAGING, UPLOADED, FAILED):
    d.mkdir(parents=True, exist_ok=True)

# transfer D-Bus path -> dest Path
_transfers = {}


def on_properties_changed(interface, changed, invalidated, path=None):
    if interface != 'org.bluez.obex.Transfer1':
        return
    status = str(changed.get('Status', ''))
    if status not in ('complete', 'error'):
        return

    dest = _transfers.pop(str(path), None)
    if dest is None:
        return

    if status == 'error':
        print(f'  transfer error for {dest.name}', flush=True)
        if dest.exists():
            dest.rename(FAILED / dest.name)
        return

    upload(dest)


def upload(path: Path):
    try:
        if not path.exists():
            print(f'  missing completed file: {path}', flush=True)
            return

        size = path.stat().st_size
        if size == 0:
            print(f'  completed but empty: {path.name}', flush=True)
            path.rename(FAILED / path.name)
            return

        print(f'  uploading {path.name} ({size:,} bytes)…', end='', flush=True)
        with path.open('rb') as f:
            r = requests.post(
                BACKEND,
                files={'image': (path.name, f, 'image/jpeg')},
                data={'source': 'phone'},
                auth=AUTH,
                timeout=30,
            )
        if r.status_code in (200, 201):
            print(' ✓', flush=True)
            path.rename(UPLOADED / path.name)
        else:
            print(f' ✗ {r.status_code}: {r.text[:120]}', flush=True)
            path.rename(FAILED / path.name)
    except Exception as e:
        print(f' ✗ {e}', flush=True)
        try:
            if path.exists():
                path.rename(FAILED / path.name)
        except Exception:
            pass


class ObexAgent(dbus.service.Object):
    def __init__(self, bus):
        super().__init__(bus, AGENT_PATH)
        self._bus = bus

    @dbus.service.method('org.bluez.obex.Agent1', in_signature='', out_signature='')
    def Release(self):
        pass

    @dbus.service.method('org.bluez.obex.Agent1', in_signature='o', out_signature='s')
    def AuthorizePush(self, transfer_path):
        obj   = self._bus.get_object('org.bluez.obex', transfer_path)
        props = dbus.Interface(obj, 'org.freedesktop.DBus.Properties')
        tx    = props.GetAll('org.bluez.obex.Transfer1')

        name      = str(tx.get('Name', f'{int(time.time())}.jpg'))
        safe_name = Path(name).name

        if not safe_name.lower().endswith(('.jpg', '.jpeg')):
            print(f'Rejected: {safe_name}', flush=True)
            raise dbus.exceptions.DBusException(
                'Rejected', name='org.bluez.obex.Error.Rejected'
            )

        # use timestamp prefix to avoid collisions
        dest = STAGING / f'{time.time_ns()}-{safe_name}'
        _transfers[str(transfer_path)] = dest
        print(f'Accepting: {safe_name} → {dest.name}', flush=True)
        return str(dest)

    @dbus.service.method('org.bluez.obex.Agent1', in_signature='', out_signature='')
    def Cancel(self):
        print('Transfer cancelled.', flush=True)


def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SessionBus()

    agent   = ObexAgent(bus)
    manager = dbus.Interface(
        bus.get_object('org.bluez.obex', '/org/bluez/obex'),
        'org.bluez.obex.AgentManager1',
    )
    try:
        manager.UnregisterAgent(AGENT_PATH)
    except dbus.exceptions.DBusException:
        pass
    manager.RegisterAgent(AGENT_PATH)

    bus.add_signal_receiver(
        on_properties_changed,
        dbus_interface='org.freedesktop.DBus.Properties',
        signal_name='PropertiesChanged',
        path_keyword='path',
    )

    print('Waiting for Bluetooth file transfers…')
    print('On Android: Gallery → Share → Bluetooth → select this laptop')
    print('Ctrl-C to quit\n')

    try:
        GLib.MainLoop().run()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()

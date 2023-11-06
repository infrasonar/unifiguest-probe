import aiohttp
import logging
from urllib.parse import quote
from libprobe.asset import Asset
from libprobe.exceptions import IncompleteResultException
from libprobe.exceptions import IgnoreResultException
from lib.unificonn import get_session


DEVICE_STATE = {
    0: 'offline',
    1: 'connected',
    2: 'pending adoption',
    4: 'updating',
    5: 'provisioning',
    6: 'unreachable',
    7: 'adopting',
    8: 'deleting',
    9: 'adoption error',
    10: 'adoption failed',
    11: 'isolated',
}


def uint(val):
    if not isinstance(val, int) or val < 0:
        return
    return val


def to_int(val):
    if val is None:
        return
    return int(val)


def to_float(val):
    if val is None:
        return
    return float(val)


async def check_unifidevice(
    asset: Asset,
    asset_config: dict,
    check_config: dict
) -> dict:
    site = check_config.get('site', 'default')
    ssl = check_config.get('ssl', False)
    mac = check_config.get('mac')
    if mac in (None, ''):
        logging.error(f'missing mac address for {asset}')
        raise IgnoreResultException
    if mac.startswith('?'):
        logging.error(f'invalid mac address for {asset}')
        raise IgnoreResultException

    session, is_unifi_os = await get_session(asset, asset_config, check_config)
    uri = '/proxy/network/api/s/' if is_unifi_os else '/api/s/'
    url = f'{uri}{quote(site, safe="")}/stat/device/{quote(mac, safe="")}'
    async with aiohttp.ClientSession(**session) as session:
        async with session.get(url, ssl=ssl) as resp:
            resp.raise_for_status()
            data = await resp.json()
            assert len(data['data']), 'device not not found'

    device = data['data'][0]
    state = {}
    radio_complete, vap_complete, port_complete = True, True, True
    mac_duplicate = set()

    # same metrics is are available in the vap_table but with (most likely)
    # aggregated values
    if 'radio_table_stats' in device:
        stat = device['stat'].get('ap', {})
        radio = [
            {
                'name': radio['name'],  # str
                'cu_self_rx': radio.get('cu_self_rx'),  # int
                'cu_self_tx': radio.get('cu_self_tx'),  # int
                'cu_total': radio.get('cu_total'),  # int
                'num_sta': radio.get('num_sta'),  # int
                'radio': radio.get('radio'),  # str
                'satisfaction':
                uint(radio.get('satisfaction')),  # int/optional
                'mac_filter_rejections':   # int
                to_int(stat.get(f'{radio["name"]}-mac_filter_rejections')),
                'rx_bytes':
                to_int(stat.get(f'{radio["name"]}-rx_bytes')),  # int
                'rx_crypts':
                to_int(stat.get(f'{radio["name"]}-rx_crypts')),  # int
                'rx_dropped':
                to_int(stat.get(f'{radio["name"]}-rx_dropped')),  # int
                'rx_errors':
                to_int(stat.get(f'{radio["name"]}-rx_errors')),  # int
                'rx_frags':
                to_int(stat.get(f'{radio["name"]}-rx_frags')),  # int
                'tx_bytes':
                to_int(stat.get(f'{radio["name"]}-tx_bytes')),  # int
                'tx_dropped':
                to_int(stat.get(f'{radio["name"]}-tx_dropped')),  # int
                'tx_errors':
                to_int(stat.get(f'{radio["name"]}-tx_errors')),  # int
                'tx_packets':
                to_int(stat.get(f'{radio["name"]}-tx_packets')),  # int
                'tx_power': radio.get('tx_power'),  # int
                'tx_retries':
                to_int(stat.get(f'{radio["name"]}-tx_retries')),  # int
            }
            for radio in device['radio_table_stats'] if radio.get('name')
        ]
        radio_complete = len(radio) == len(device['radio_table_stats'])
        state['radio'] = radio

    if 'vap_table' in device:
        vap = [
            {
                'name': vap['name'],  # str
                'bssid': vap.get('bssid'),  # str
                'channel': vap.get('channel'),  # int
                'essid': vap.get('essid'),  # str
                'extchannel': vap.get('extchannel'),  # int/optional
                'num_sta': vap.get('num_sta'),  # int
                'radio_name': vap.get('radio_name'),  # str + ref
                'rx_bytes': vap.get('rx_bytes'),  # int
                'rx_crypts': vap.get('rx_crypts'),  # int
                'rx_dropped': vap.get('rx_dropped'),  # int
                'rx_errors': vap.get('rx_errors'),  # int
                'rx_frags': vap.get('rx_frags'),  # int
                'tx_bytes': vap.get('tx_bytes'),  # int
                'tx_dropped': vap.get('tx_dropped'),  # int
                'tx_errors': vap.get('tx_errors'),  # int
                'tx_power': vap.get('tx_power'),  # int
                'satisfaction': uint(vap.get('satisfaction')),  # int/opt
            }
            for vap in device['vap_table'] if 'name' if vap.get('name')
        ]
        vap_complete = len(vap) == len(device['vap_table'])
        state['vap'] = vap

    if 'uplink' in device:
        uplink = device['uplink']
        item = {
            'name': uplink['name'],  # str
            'full_duplex': uplink['full_duplex'],  # bool
            'ip': uplink.get('ip'),  # str/opt
            'mac': uplink['mac'],  # str
            'max_speed': uplink['max_speed'],  # int
            'netmask': uplink.get('netmask'),  # str/opt
            'num_port': uplink['num_port'],  # int
            'port_idx': uplink.get('port_idx'),  # int/opt
            'rx_bytes': uplink['rx_bytes'],  # int
            'rx_dropped': uplink['rx_dropped'],  # int
            'rx_errors': uplink['rx_errors'],  # int
            'rx_multicast': uplink['rx_multicast'],  # int
            'rx_packets': uplink['rx_packets'],  # int
            'speed': uplink['speed'],  # int
            'tx_bytes': uplink['tx_bytes'],  # int,
            'tx_dropped': uplink['tx_dropped'],  # int
            'tx_errors': uplink['tx_errors'],  # int
            'tx_packets': uplink['tx_packets'],  # int
            'type': uplink['type'],  # str, eg. wire
            'uplink_device_name': uplink.get('uplink_device_name'),  # str/opt
            'uplink_mac': uplink.get('uplink_mac'),  # str/opt
            'uplink_remote_port': uplink.get('uplink_remote_port'),  # int/opt
            'uplink_source': uplink.get('uplink_source'),  # str/opt
        }
        state['uplink'] = [item]

    if 'port_table' in device:
        mac_set = set()  # check for duplicates
        mac_table = []
        port_table = []
        for port in device['port_table']:
            if port.get('name') is None:
                port_complete = False
                continue
            port_table.append({
                'name': port['name'],  # str
                'port_idx': port.get('port_idx'),  # int/opt
                'poe_caps': port['poe_caps'],  # int
                'poe_mode': port.get('poe_mode'),  # str/opt, e.g. auto
                'port_poe': port['port_poe'],  # bool
                'poe_good': port.get('poe_good'),  # bool/opt
                'poe_power': to_float(port.get('poe_power')),  # float/opt
                'media': port['media'],  # str, e.g. GE
                'op_mode': port['op_mode'],  # str, e.g. switch
                'autoneg': port['autoneg'],  # bool
                'speed_caps': port['speed_caps'],  # int
                'forward': port['forward'],  # str, e.g. all
                'enable': port['enable'],  # bool
                'full_duplex': port['full_duplex'],  # bool
                'is_uplink': port['is_uplink'],  # bool
                'up': port['up'],  # bool
                'masked': port['masked'],  # bool
                'flowctrl_rx': port['flowctrl_rx'],  # bool
                'flowctrl_tx': port['flowctrl_tx'],  # bool
                'jumbo': port['jumbo'],  # bool
                'speed': port['speed'],  # int  e.g. 100 or 1000
                'stp_pathcost': port['stp_pathcost'],  # int
                'stp_state': port['stp_state'],  # str e.g. forwarding
                'satisfaction': port.get('satisfaction'),  # int/opt
                'rx_broadcast': port['rx_broadcast'],  # int
                'rx_bytes': port['rx_bytes'],  # int
                'rx_dropped': port['rx_dropped'],  # int
                'rx_errors': port['rx_errors'],  # int
                'rx_multicast': port['rx_multicast'],  # int
                'rx_packets': port['rx_packets'],  # int
                'tx_broadcast': port['tx_broadcast'],  # int
                'tx_bytes': port['tx_bytes'],  # int
                'tx_dropped': port['tx_dropped'],  # int
                'tx_errors': port['tx_errors'],  # int
                'tx_multicast': port['tx_multicast'],  # int
                'tx_packets': port['tx_packets'],  # int
            })
            for mac in port['mac_table']:
                if mac['mac'] in mac_set:
                    mac_duplicate.add(mac['mac'])
                    continue
                mac_set.add(mac['mac'])
                mac_table.append({
                    'name': mac['mac'],  # str, mac-address
                    'port_name': port['name'],  # str, -> reference port table
                    'age': mac['age'],  # int
                    'ip': mac.get('ip'),  # str/opt
                    'uptime': mac['uptime'],  # int
                    'vlan': mac['vlan'],  # int
                    'static': mac['static'],  # bool
                })
        state['port'] = port_table
        state['mac'] = mac_table

    config_network = device.get('config_network', {})
    item = {
        'name': device['name'],  # str
        'mac': device.get('mac'),  # str
        'state': DEVICE_STATE.get(device.get('state')),  # str
        'adopted': device.get('adopted'),  # bool
        'type': device.get('type'),  # str
        'model': device.get('model'),  # str
        'num_sta': device.get('num_sta'),  # int
        'ip': device.get('ip'),  # str
        'isolated': device.get('isolated'),  # bool
        'uplink': device.get('uplink', {}).get('name'),  # str
        'version': device.get('version'),  # str
        'uptime': device.get('uptime'),  # int
        'cpu': to_float(device.get('system-stats', {}).get('cpu')),
        'mem': to_float(device.get('system-stats', {}).get('mem')),
        'satisfaction': uint(device.get('satisfaction')),  # int/optional
        'total_used_power': device.get('total_used_power'),  # float/opt
        'config_network_type': config_network.get('type'),  # str/opt, eg dhcp
        'bonding_enabled': config_network.get('bonding_enabled'),  # bool/opt
        'kernel_version': device.get('kernel_version'),  # str/opt
        'serial': device.get('serial'),  # str/opt
        'license_state': device.get('license_state'),  # str/opt
    }

    state['device'] = [item]

    if not radio_complete:
        raise IncompleteResultException('At least one radio without a name',
                                        result=state)
    if not vap_complete:
        raise IncompleteResultException('At least one VAP without a name',
                                        result=state)
    if not port_complete:
        raise IncompleteResultException('At least one Port without a name',
                                        result=state)
    if mac_duplicate:
        if len(mac_duplicate) > 5:
            msg = f'{len(mac_duplicate)} duplicates found'
        else:
            msg = f'{", ".join(mac_duplicate)}'
        raise IncompleteResultException(
            f'The same MAC address detected on multiple ports ({msg})',
            result=state)
    return state

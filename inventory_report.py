#!/usr/bin/env python

"""Script to export Inventory Data for Virtual Services, Pools and SEs."""

import argparse
import csv
import getpass

import requests
import urllib3
from avi.sdk.avi_api import ApiSession
from tabulate import tabulate

# Disable certificate warnings

if hasattr(requests.packages.urllib3, 'disable_warnings'):
    requests.packages.urllib3.disable_warnings()

if hasattr(urllib3, 'disable_warnings'):
    urllib3.disable_warnings()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('-c', '--controller',
                        help='FQDN or IP address of Avi Controller')
    parser.add_argument('-u', '--user', help='Avi API Username',
                        default='admin')
    parser.add_argument('-p', '--password', help='Avi API Password')
    parser.add_argument('-t', '--tenant', help='Tenant',
                        default='admin')
    parser.add_argument('-x', '--apiversion', help='Avi API version')
    parser.add_argument('-i', '--inventorytype',
                        help='Inventory type (vs, pool, pooldetail, se, sedetail)',
                        choices=['vs', 'pool', 'pooldetail', 'se', 'sedetail'],
                        default='vs')
    parser.add_argument('-f', '--file', help='Output to named CSV file ')

    args = parser.parse_args()

    if args:
        # If not specified on the command-line, prompt the user for the
        # controller IP address and/or password

        controller = args.controller
        user = args.user
        password = args.password
        tenant = args.tenant
        api_version = args.apiversion
        inventory_type = args.inventorytype
        csv_filename = args.file

        while not controller:
            controller = input('Controller:')

        while not password:
            password = getpass.getpass(f'Password for {user}@{controller}:')

        if not api_version:
            # Discover Controller's version if no API version specified

            api = ApiSession.get_session(controller, user, password)
            api_version = api.remote_api_version['Version']
            api.delete_session()
            print(f'Discovered Controller version {api_version}.')
        api = ApiSession.get_session(controller, user, password,
                                     api_version=api_version)
        output_table = []
        headers = []

        if inventory_type == 'vs':
            vs_inventory = api.get_objects_iter('virtualservice-inventory',
                                                params={'include_name': True},
                                                tenant=tenant)
            for vs in vs_inventory:
                vs_config = vs['config']
                vs_runtime = vs['runtime']
                vs_name = vs_config['name']
                vs_uuid = vs_config['uuid']
                vs_type = vs_config['type'].split('VS_TYPE_')[1]
                vs_seg = vs_config['se_group_ref'].split('#')[1]
                vs_tenant = vs_config['tenant_ref'].split('#')[1]
                vs_cloud = vs_config['cloud_ref'].split('#')[1]
                vs_vrf = vs_config['vrf_context_ref'].split('#')[1]
                vs_ports = [(s['port'], s['port_range_end'], s['enable_ssl'])
                            for s in vs_config['services']]
                vs_ports = ','.join([f'{a}' + ('' if a == b else f'-{b}') +
                                     ('*' if c else '')
                                     for (a, b, c) in vs_ports])
                vs_waf = vs_config.get('waf_policy_ref', '#').split('#')[1]
                vs_app_profile_type = vs.get('app_profile_type',
                                             'APPLICATION_PROFILE_TYPE_UNKNOWN')
                vs_app_type = vs_app_profile_type.split(
                    'APPLICATION_PROFILE_TYPE_')[1]
                all_ip_addresses = []
                if vs_config['type'] == 'VS_TYPE_VH_CHILD':
                    for v in vs.get('parent_vs_vip', []):
                        all_ip_addresses.extend([v[ip_type]['addr']
                                    for ip_type in ('ip_address', 'ip6_address')
                                    if ip_type in v])
                    vs_fqdns = ','.join(vs_config.get('vh_domain_name', []))
                else:
                    for v in vs_config.get('vip', []):
                        all_ip_addresses.extend([v[ip_type]['addr']
                                    for ip_type in ('ip_address', 'ip6_address')
                                    if ip_type in v])
                    vs_fqdns = ','.join([d['fqdn']
                                        for d in vs_config.get('dns_info', [])])
                vs_vips = ','.join(all_ip_addresses)
                vs_selist = set()
                if 'vip_summary' in vs_runtime:
                    for v in vs_runtime['vip_summary']:
                        if 'service_engine' in v:
                            vs_selist.update(s['url'].split('#')[1]
                                             for s in v['service_engine'])
                vs_selist = ','.join(vs_selist)
                vs_enabled = 'Enabled' if vs_config['enabled'] else 'Disabled'
                vs_state = vs_runtime['oper_status']['state'].split('OPER_')[1]
                vs_hs = vs['health_score']['health_score']
                vs_pools = ','.join([p.split('#')[1] for p in vs['pools']])
                vs_poolgroups = ','.join([pg.split('#')[1]
                                         for pg in vs['poolgroups']])
                output_table.append([vs_name, vs_uuid, vs_tenant, vs_cloud,
                                     vs_vrf, vs_type, vs_seg, vs_vips, vs_fqdns,
                                     vs_ports, vs_pools, vs_poolgroups,
                                     vs_app_type, vs_waf, vs_enabled,
                                     vs_state, vs_hs, vs_selist])
            headers = ['Name', 'UUID', 'Tenant', 'Cloud', 'VRF', 'Type', 'SEG',
                       'VIPs', 'FQDNs', 'Ports', 'Pools', 'Pool Groups',
                       'App Type', 'WAF', 'State', 'Oper State', 'Health Score',
                       'Service Engines']
        elif inventory_type in ('pool', 'pooldetail'):
            p_inventory = api.get_objects_iter('pool-inventory',
                                               params={'include_name': True},
                                               tenant=tenant)
            for p in p_inventory:
                p_config = p['config']
                p_runtime = p['runtime']
                p_name = p_config['name']
                p_uuid = p_config['uuid']
                p_tenant = p_config['tenant_ref'].split('#')[1]
                p_cloud = p_config['cloud_ref'].split('#')[1]
                p_vrf = p_config['vrf_ref'].split('#')[1]
                p_port = p_config['default_server_port']
                p_servers = p_config['num_servers']
                p_state = p_runtime['oper_status']['state'].split('OPER_')[1]
                p_hs = p['health_score']['health_score']
                p_vs = ','.join([vs.split('#')[1]
                                 for vs in p.get('virtualservices', [])])

                output = [p_name, p_uuid, p_tenant, p_cloud, p_vrf, p_port,
                          p_servers, p_state, p_hs, p_vs]

                if inventory_type == 'pooldetail':
                    ps_inventory = api.get_objects_iter(
                        f'pool-inventory/{p_uuid}/server',
                        params={'include_name': True},
                        tenant=tenant)
                    p_servers = [(ps['config']['ip']['addr'],
                                  ps['config']['port'],
                                  ps['runtime']['oper_status']['state'].split(
                        'OPER_')[1],
                        ps['health_score']['health_score'])
                        for ps in ps_inventory]

                    output.append(','.join([f'{a}' +
                                            (f':{b}' if b != p_port else '') +
                                            f' [{c},{d}]'
                                            for (a, b, c, d) in p_servers]))

                    vs_selist = set()
                    for vs in p.get('virtualservices', []):
                        vs_uuid = vs.split('/api/virtualservice/')[1]
                        rsp = api.get(
                            f'virtualservice-inventory/{vs_uuid}',
                            params={'include_name': True},
                            tenant=tenant)

                        if rsp.status_code < 300:
                            vs_runtime = rsp.json().get('runtime', {})
                        else:
                            vs_runtime = {}

                        if 'vip_summary' in vs_runtime:
                            for v in vs_runtime['vip_summary']:
                                if 'service_engine' in v:
                                    vs_selist.update(s['url'].split('#')[1]
                                                for s in v['service_engine'])
                    output.append(','.join(vs_selist))

                output_table.append(output)
            headers = ['Name', 'UUID', 'Tenant', 'Cloud', 'VRF', 'Port',
                       '#Servers', 'State', 'Health Score', 'Virtual Services']
            if inventory_type == 'pooldetail':
                headers.extend(['Servers', 'Service Engines'])
        elif inventory_type in ('se', 'sedetail'):
            if inventory_type == 'sedetail':
                s_objects = api.get_objects_iter('serviceengine',
                                    params={'include_name': True,
                                    'fields': 'resources'},
                                    tenant=tenant)
                s_details = {s['uuid']: s['resources'] for s in s_objects}

            s_inventory = api.get_objects_iter('serviceengine-inventory',
                                               params={'include_name': True},
                                               tenant=tenant)

            for s in s_inventory:
                s_config = s['config']
                s_runtime = s['runtime']
                s_name = s_config['name']
                s_uuid = s_config['uuid']
                s_tenant = s_config['tenant_ref'].split('#')[1]
                s_cloud = s_config['cloud_ref'].split('#')[1]
                s_seg = s_config['se_group_ref'].split('#')[1]
                s_enabled = s_config['enable_state'].split('SE_STATE_')[1]
                s_state = s_runtime['oper_status']['state'].split('OPER_')[1]
                s_connected = ('Connected' if s_runtime['se_connected']
                               else 'Not connected')
                s_version = s_runtime['version']
                s_online = s_runtime['online_since']
                s_hs = s['health_score']['health_score']
                s_vs = ','.join([v.split('#')[1]
                                 for v in s_config['virtualservice_refs']])

                output = [s_name, s_uuid, s_tenant, s_cloud, s_seg, s_enabled,
                          s_state, s_connected, s_version, s_online, s_hs,
                          s_vs]

                if inventory_type == 'sedetail':
                    s_detail = s_details.get(s_uuid, {})
                    s_vcpu = s_detail.get('num_vcpus', '-')
                    s_memory = s_detail.get('memory', '-')
                    s_disk = s_detail.get('disk', '-')
                    s_qat = s_detail.get('qat_mode', 'QAT_N/A').split('QAT_')[1]
                    output.extend([s_vcpu, s_memory, s_disk, s_qat])

                output_table.append(output)

            headers = ['Name', 'UUID', 'Tenant', 'Cloud', 'SEG', 'State',
                       'Oper State', 'Connectivity', 'Version', 'Online Since',
                       'Health Score', 'Virtual Services']

            if inventory_type == 'sedetail':
                headers.extend(['vCPUs', 'Memory (MB)', 'Disk (GB)',
                                'QAT Mode'])
        if csv_filename:
            print(f'Outputting data to {csv_filename}')
            with open(csv_filename, 'w',
                      newline='', encoding='UTF-8') as csv_file:
                csv_writer = csv.writer(csv_file, dialect='excel')
                csv_writer.writerow(headers)
                csv_writer.writerows(output_table)
        else:
            print(tabulate(output_table, headers=headers, tablefmt='outline'))

    else:
        parser.print_help()

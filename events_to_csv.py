#!/usr/bin/env python

"""Script to export Virtual Service Client Logs to a CSV file."""

import argparse
import csv
import getpass
from datetime import datetime, timezone
from os import devnull

import requests
import urllib3
from avi.sdk.avi_api import ApiSession

# Disable certificate warnings

if hasattr(requests.packages.urllib3, 'disable_warnings'):
    requests.packages.urllib3.disable_warnings()

if hasattr(urllib3, 'disable_warnings'):
    urllib3.disable_warnings()

def get_query_id():
    return int(100*datetime.now().timestamp())

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
    parser.add_argument('-f', '--filename', help='Output to named CSV file')
    parser.add_argument('-fs', '--filterstring', help='Filter String',
                        action='append')
    parser.add_argument('startdatetime',
                        help='Start date and time for exported logs '
                             'in ISO8601 format, e.g. 2024-01-01T00:00.')
    parser.add_argument('enddatetime',
                        help='Start date and time for exported logs '
                             'in ISO8601 format, e.g. 2024-01-01T00:00.')

    args = parser.parse_args()

    if args:
        # If not specified on the command-line, prompt the user for the
        # controller IP address and/or password

        controller = args.controller
        user = args.user
        password = args.password
        tenant = args.tenant
        api_version = args.apiversion
        filename = args.filename or devnull
        filterstrings = args.filterstring

        params = { 'type': 2 }

        start_date_time = (datetime.fromisoformat(args.startdatetime)
                           .astimezone(timezone.utc))
        end_date_time = (datetime.fromisoformat(args.enddatetime)
                         .astimezone(timezone.utc))

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

        field_names = ['report_timestamp', 'obj_type', 'event_id',
                       'module', 'internal', 'context' 'obj_uuid',
                       'obj_name', 'event_details']

        params['page_size'] = 10000
        params['page'] = 1
        params['type'] = 2
        params['start'] = start_date_time.isoformat(timespec='microseconds')
        params['end'] = end_date_time.isoformat(timespec='microseconds')
        params['format'] = 'json'

        if filterstrings:
            params['filter'] = filterstrings

        total_logs = 0
        last_results = []

        print(f':: Writing to file {filename}...')

        with (open(filename, 'w', newline='', encoding='UTF-8')) as csv_file:
            csv_writer = csv.writer(csv_file, dialect='excel')
            csv_writer.writerow(field_names)

            while True:
                print(f':: Retrieving up to 10,000 logs from '
                      f'{start_date_time:%c %Z} to '
                      f'{end_date_time:%c %Z}...')

                params['query_id'] = get_query_id()
                params['end'] = end_date_time.isoformat(timespec='microseconds')

                r = api.get('analytics/logs', tenant=tenant, params=params)
                if r.status_code == 200:
                    r_data = r.json()
                    results = r_data['results']
                    res_count = len(results)

                    if res_count > 0:
                        # To avoid missing logs when there are multiple logs
                        # with the same timestamp spanning two consecutive
                        # retrievals, we set the end time of the query equal to
                        # the timestamp of the last result of the previous
                        # query. This will result in an overlap of one or more
                        # logs between the two queries, so we need to remove
                        # this overlap.

                        check = 1
                        slice_from = 0

                        old_res_count = len(last_results)

                        ts_new = datetime.fromisoformat(
                            results[0]['report_timestamp'])

                        while check <= res_count and check <= old_res_count:
                            ts_check = datetime.fromisoformat(
                                last_results[-check]['report_timestamp'])
                            if ts_check < ts_new:
                                break
                            if results[:check] == last_results[-check:]:
                                slice_from = check

                            check += 1

                        if slice_from > 0:
                            results = results[slice_from:]
                            res_count = len(results)

                    if res_count > 0:
                        print(f'  Got {res_count} logs')
                        for res in results:
                            vals = ["'" + str(v) if v is not None and
                                    str(v).lstrip().startswith(('+', '-', '='))
                                    else v for v in [res.get(f, None)
                                                     for f in field_names]]
                            csv_writer.writerow(vals)
                        total_logs += res_count
                        last_entry = results[-1]['report_timestamp']
                        end_date_time = datetime.fromisoformat(last_entry)
                        last_results = results
                    else:
                        print(':: No more logs available')
                        break
                else:
                    print(f':: Error {r.status_code} {r.text} occurred '
                          f': giving up!')
                    break
        print(f':: {total_logs} logs were retrieved')
    else:
        parser.print_help()

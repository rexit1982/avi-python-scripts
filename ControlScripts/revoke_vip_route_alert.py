#!/usr/bin/python3

"""Schedule this ControlScript to run on VS events (e.g. VS_CREATE, VS_UP) to set revoke_vip_route to true for VSs in NSX clouds"""

import os
import json
import sys
from avi.sdk.avi_api import ApiSession
import urllib3
import requests

if hasattr(requests.packages.urllib3, 'disable_warnings'):
    requests.packages.urllib3.disable_warnings()

if hasattr(urllib3, 'disable_warnings'):
    urllib3.disable_warnings()

def ParseAviParams(argv):
    if len(argv) != 2:
        return {}
    
    try:
        alert_params = json.loads(argv[1])
        return alert_params
    except json.JSONDecodeError:
        return {}

def get_api_token():
    return os.environ.get('API_TOKEN')

def get_api_user():
    return os.environ.get('USER')

def get_api_endpoint():
    return os.environ.get('DOCKER_GATEWAY') or 'localhost'

if __name__ == '__main__':
    # Grab top level information from the alert argument 
    alert_params = ParseAviParams(sys.argv)
    events = alert_params.get('events', [])
    
    if not events:
        print("No events found in payload.")
        sys.exit()

    objuuid = events[0].get('obj_uuid')

    api_endpoint = get_api_endpoint()
    user = get_api_user()
    token = get_api_token()

    with ApiSession(api_endpoint, user, token=token, tenant='*',api_version='30.2.1') as session:
        
        # Query the Virtual Service
        resp = session.get(f'virtualservice/{objuuid}?fields=name,revoke_vip_route,cloud_type')
        
        # Check if the API call was successful
        if resp.status_code >= 300:
            print(f'Unable to locate Virtual Service {objuuid}. API returned {resp.status_code}')
            sys.exit()    
            
        vs = resp.json()

        # Safely check the cloud type
        if vs.get('cloud_type') != 'NSXT_CLOUD':
            print("VS is not in an NSX-T Cloud. Exiting.")
            sys.exit()  
        
        # Safely check the boolean value (no quotes)
        if vs.get('revoke_vip_route') is True:
            print("revoke_vip_route is already True. Exiting.")
            sys.exit()

        # Build the patch payload using native booleans
        patch_data = {
            'json_patch': [
                {
                    'op': 'replace',
                    'path': '/revoke_vip_route',
                    'value': True
                }
            ]
        }

        # Apply the patch
        upd = session.patch(f'virtualservice/{objuuid}', data=json.dumps(patch_data),api_version='30.2.1')
        
        if upd.status_code != 200:
            # Write to stderr so the Avi Controller flags it as an error in the logs
            print(f'Failed to update Virtual Service {vs.get("name")} with error code {upd.status_code} and message {upd.text}', file=sys.stderr)
        else:
            print(f'Successfully updated {vs.get("name")}')
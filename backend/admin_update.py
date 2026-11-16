"""Update the demo shipping status using the private admin secret (no public UI)."""
import os
import sys
import urllib.request
import json

if len(sys.argv) not in (3, 4):
    print('Usage: python backend/admin_update.py DEMO-ORDER-ID packing|shipped|delivered [tracking_code]')
    raise SystemExit(2)
key = os.environ.get('SAGEMAKER_ADMIN_KEY', '')
if not key:
    print('Set SAGEMAKER_ADMIN_KEY in the terminal where you run this command.')
    raise SystemExit(2)
url = 'http://127.0.0.1:8000/api/legacy/admin/orders/' + sys.argv[1] + '/status'
data = {'status': sys.argv[2]}
if len(sys.argv) == 4:
    data['tracking_number'] = sys.argv[3]
req = urllib.request.Request(url, data=json.dumps(data).encode(), method='PATCH', headers={'Content-Type': 'application/json', 'X-Admin-Key': key})
with urllib.request.urlopen(req) as response:
    print(response.read().decode())

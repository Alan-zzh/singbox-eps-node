import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
os.chdir('/root/singbox-eps-node')
from dotenv import load_dotenv
load_dotenv('/root/singbox-eps-node/.env')

from subscription_service import get_cdn_ip_for_protocol, generate_all_links, CDN_MODE, CF_DOMAIN, SERVER_IP

with open('/tmp/test_sub2.txt', 'w') as f:
    f.write(f"CDN_MODE={CDN_MODE}\n")
    f.write(f"SERVER_IP={SERVER_IP}\n")
    f.write(f"CF_DOMAIN={CF_DOMAIN}\n")
    for key in ['vless_ws_cdn_ip', 'vless_upgrade_cdn_ip', 'trojan_ws_cdn_ip']:
        result = get_cdn_ip_for_protocol(key)
        f.write(f"get_cdn_ip_for_protocol('{key}') = {result}\n")
    links = generate_all_links()
    for link in links:
        if 'WS' in link or 'Upgrade' in link or 'Trojan' in link:
            addr = link.split('@')[1].split(':')[0] if '@' in link else 'PARSE_ERR'
            f.write(f"CDN addr in link: {addr}\n")

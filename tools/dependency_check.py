"""Inspect declared external requirements; optional HTTPS checks never execute tools."""
import argparse,importlib.util,ipaddress,json,socket,sys,urllib.error,urllib.parse,urllib.request
from pathlib import Path

def check_links(urls):
    results=[]
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    opener=urllib.request.build_opener(NoRedirect)
    for url in sorted(set(urls)):
        parsed=urllib.parse.urlsplit(url)
        display=urllib.parse.urlunsplit((parsed.scheme,parsed.hostname or '',parsed.path,'',''))
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:
            results.append({'url':display,'ok':False,'reason':'Only public HTTPS source URLs are permitted'});continue
        try:
            current=url
            for _ in range(6):
                parsed=urllib.parse.urlsplit(current)
                if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:raise ValueError('Unsafe redirect')
                addresses={row[4][0] for row in socket.getaddrinfo(parsed.hostname,443)}
                if any(not ipaddress.ip_address(a).is_global for a in addresses):raise ValueError('Non-public destination')
                request=urllib.request.Request(current,headers={'User-Agent':'DCRC-dependency-link-check'})
                try:response=opener.open(request,timeout=15)
                except urllib.error.HTTPError as error:
                    if error.code in (301,302,303,307,308) and error.headers.get('Location'):
                        current=urllib.parse.urljoin(current,error.headers['Location']);continue
                    raise
                with response:
                    response.read(1);results.append({'url':display,'ok':True,'status':response.status})
                break
            else:raise ValueError('Redirect limit')
        except (OSError,ValueError,urllib.error.URLError) as error:
            results.append({'url':display,'ok':False,'reason':type(error).__name__})
    return results

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--links',action='store_true',help='Check public source/licence URLs; no downloads are executed')
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    catalog=json.loads((root/'dependencies.json').read_text(encoding='utf-8'))
    report={'python_supported':sys.version_info>=(3,11),
        'installed':{name:importlib.util.find_spec(name)is not None for name in ('PIL','elftools','PySide6','pytest')},
        'dependencies':len(catalog['dependencies']),
        'notice':'Missing/dead dependencies require the dependency-research skill; no private SDK is assumed.'}
    if args.links:
        urls=[d[k] for d in catalog['dependencies'] for k in ('source','licence_url') if d.get(k)]
        report['links']=check_links(urls)
    print(json.dumps(report,indent=2));return 0 if report['python_supported'] and all(v['ok']for v in report.get('links',[])) else 1
if __name__=='__main__':raise SystemExit(main())

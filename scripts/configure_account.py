"""Write a local account pin, never read messages, extract keys or overwrite config."""
import argparse
import json
import pathlib


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=pathlib.Path,required=True)
    parser.add_argument('--db-dir',type=pathlib.Path,required=True)
    parser.add_argument('--account',required=True)
    args=parser.parse_args()
    runtime=args.runtime.expanduser().resolve()
    root=args.db_dir.expanduser().resolve()
    account=args.account
    if not account or account in ('.','..') or pathlib.Path(account).name!=account or '/' in account or '\\' in account:
        parser.error('Account must be a single explicitly selected directory name.')
    selected=(root/account).resolve()
    if selected.parent!=root or not (selected/'db_storage').is_dir():
        parser.error('Selected account database directory is unavailable.')
    if not (runtime/'server.py').is_file():
        parser.error('Runtime is not installed at the supplied path.')
    config=runtime/'private_config.json'
    with config.open('x',encoding='utf-8') as stream:
        json.dump({'db_dir':str(root),'account':account},stream,ensure_ascii=False)
    print('Pinned the selected local account. No messages read, keys extracted, or existing configuration overwritten.')


if __name__=='__main__':main()

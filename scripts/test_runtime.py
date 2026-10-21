"""Run synthetic runtime tests without opening WeChat or extracting account keys."""
import argparse
import pathlib
import site
import sys
import unittest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime',type=pathlib.Path)
    parser.add_argument('--dependency-dir',type=pathlib.Path)
    args=parser.parse_args()
    runtime=(args.runtime or pathlib.Path(__file__).resolve().parents[1]/'assets/mcp-runtime').resolve()
    sys.dont_write_bytecode=True
    site.addsitedir(str(args.dependency_dir or runtime/'lib'))
    sys.path.insert(0,str(runtime))
    suite=unittest.defaultTestLoader.discover(str(runtime/'tests'))
    result=unittest.TextTestRunner(verbosity=1).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__=='__main__':main()

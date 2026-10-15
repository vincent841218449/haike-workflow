"""Enable only local curated TTS production; never configures a cloud host."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backlot.studio import Studio, atomic_private
from backlot.studio_system_voice import status


def main():
    parser = argparse.ArgumentParser(description="本机系统音色配音开关，不发起收费调用")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--enable", action="store_true")
    group.add_argument("--disable", action="store_true")
    args = parser.parse_args()
    studio = Studio(ROOT / "projects")
    if args.enable or args.disable:
        atomic_private(studio.private / "haike-api/system-voices.local.json", {"enabled": args.enable})
    print(json.dumps(status(studio), ensure_ascii=False))


if __name__ == "__main__":
    main()

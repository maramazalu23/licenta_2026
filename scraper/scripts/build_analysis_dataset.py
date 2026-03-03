import subprocess
import sys

def run_module(mod: str):
    cmd = [sys.executable, "-m", mod]
    print(">>", " ".join(cmd))
    r = subprocess.run(cmd)
    if r.returncode != 0:
        raise SystemExit(r.returncode)

def main():
    run_module("scripts.build_clean_table")
    run_module("scripts.normalize_clean")
    run_module("scripts.create_products_analysis_view")
    run_module("scripts.checks.check_analysis_view")
    print("analysis dataset: OK")

if __name__ == "__main__":
    main()
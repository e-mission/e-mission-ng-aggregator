import argparse
import json
import subprocess
import shared_apis.service_router_api as sasra

def main(input_file, query_file, secret_key):

    # Make sure the network is launched on all machines
    sasra.setup_networks()

    # Run the launch PM script
    res = subprocess.run(["./e-mission-py.bash", "client_scripts/launch_pm.py", secret_key], stdout=subprocess.PIPE, encoding="utf-8")
    pm_address = res.stdout.strip()

    # Generate a consistent uuid value
    uuid = "23"

    # Run the upload script
    subprocess.run(["./e-mission-py.bash", "client_scripts/upload_data.py", input_file, uuid, pm_address])

    # Run the pipeline script
    subprocess.run(["./e-mission-py.bash", "client_scripts/run_pipeline.py", uuid, pm_address])

    res = subprocess.run(["./e-mission-py.bash", "client_scripts/run_count.py", uuid, pm_address, query_file], stdout=subprocess.PIPE, encoding="utf-8")

    # Forward the results of the count query
    print(res.stdout.strip())

    # Delete the PM
    sasra.delete_service(pm_address)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='''
            Example script to run all the example script steps
            ''')
    parser.add_argument("input_file", type=str,
        help='''
            the input json file for the user
        ''')
    parser.add_argument("query_file", type=str,
        help='''
            the input file for the user's query
        ''')
    parser.add_argument("secret_key", type=str,
        help='''
            the secret key used to encrypt user data
        ''')
    args = parser.parse_args()
    main(args.input_file, args.query_file, args.secret_key)

import json
import numpy as np
from shared_apis.bottle import route, post, get, run, template, static_file, request, app, HTTPError, abort, BaseRequest, JSONPlugin, response
import shared_apis.bottle as bt
import sys

import time
# So that we can set the socket timeout
import socket

import requests

import service_router.launcher as srl
from conf.machine_configs import service_router_ip, service_router_port, service_router_tls, upc_mode, machines_use_tls, certificate_bundle_path

BaseRequest.MEMFILE_MAX = 1024 * 1024 * 1024 # Allow the request size to be 1G
# to accomodate large section sizes

app = app()

# List of all supported services
services = None

pods = dict()

pm_name = 'PM'

@post ("/service_request")
def request_service():
    service_name = request.json["service"]
    if service_name in services:
        services_dict = services[service_name]
        if upc_mode == "kubernetes":
            service_file = services_dict['service_file']
            pod_file = services_dict['pod_file'] 
            server_container_name = services_dict['server_container_name']
        elif upc_mode == "docker":
            service_file = services_dict['compose_file']
            pod_file = None
            server_container_name = None
        else:
            raise HTTPError(403, "Unknown UPC mode. Reconfigure router with either kubernetes or docker")
    else:
        raise HTTPError(403, "Request made for an unknown service")

    # Launch the actual container
    container_name, address = srl.spawnServiceInstance (service_file, pod_file, server_container_name)
    # Solution to wait for pods to be ready. A pod is ready when we can connect.
    # Although it should reject our connection
    # To support dynamic loading of client-specific libraries
    attempt_counter = 45
    connection_failed = True
    attempt_to_connect_address = address + "/"
    while attempt_counter > 0 and connection_failed:
        try:
            if machines_use_tls:
                resp = requests.post(attempt_to_connect_address, verify=certificate_bundle_path)
            else:
                resp = requests.post(attempt_to_connect_address)
            connection_failed = False
            pods[address] = container_name
        except requests.exceptions.ConnectionError:
            attempt_counter -= 1
            time.sleep(1)
    if attempt_counter == 0:
        # We failed to connect to the server in a reasonable number of attempts
        raise HTTPError(403, "Unable to contact spawned service. Make sure your container didn't crash and connection isn't blocked by a firewall.")
    return {'address': address}

@post('/pause')
def pause_pod():
    address = request.json["address"]
    srl.pauseInstance(pods[address])

@post('/unpause')
def resume_pod():
    address = request.json["address"]
    srl.resumeInstance(pods[address])

@post('/kill')
def kill_service_and_pod():
    address = request.json["address"]
    srl.killInstance(pods[address])
    del pods[address]

@post('/clear_containers')
def clear_containers ():
    global pods
    srl.clearContainers ()
    pods = dict()

@post('/setup_networks')
def setup_networks ():
    srl.setupNetworks ()


if __name__ == "__main__":
    if len(sys.argv) != 1:
      sys.stderr.write ("Error too many arguments to launch known access location.\n")
      sys.exit(1)
    # Read the services
    if upc_mode == "kubernetes":
        service_filename = "service_router/kubernetes_services.json"
    elif upc_mode == "docker":
        service_filename = "service_router/docker_services.json"
    else:
          sys.stderr.write ("Unknown UPC mode. Reconfigure router with either kubernetes or docker.\n")
          sys.exit(1)
    with open(service_filename, "r") as f:
        services = json.load(f)


    # Place holder for SSL that will be replaced with 443 when run in a container.
    # Not controller port is set to be an integer by an earlier code segment
    if service_router_tls:
      # We support SSL and want to use it
      key_file = open('conf/keys.json')
      key_data = json.load(key_file)
      host_cert = key_data["host_certificate"]
      chain_cert = key_data["chain_certificate"]
      private_key = key_data["private_key"]

      run(host=service_router_ip, port=service_router_port, server='cheroot', debug=True,
          certfile=host_cert, chainfile=chain_cert, keyfile=private_key)
    else:
      print("Running with HTTPS turned OFF - use a reverse proxy on production")
      run(host=service_router_ip, port=service_router_port, server="cheroot", debug=True)

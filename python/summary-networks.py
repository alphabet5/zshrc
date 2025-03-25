#!/usr/bin/env python3

import sys
import ipaddress

def subtract_networks(parent_network, networks_to_subtract):
    """
    Subtract a list of networks from a parent network.
    Returns a list of resulting networks.
    """
    # Convert parent network string to an IPv4Network object
    parent = ipaddress.IPv4Network(parent_network)
    
    # Start with the parent network as the only result
    result_networks = [parent]
    
    # For each network to subtract
    for subtract_net_str in networks_to_subtract:
        subtract_net = ipaddress.IPv4Network(subtract_net_str)
        
        # Check if the network to subtract is within the parent
        if not any(subtract_net.subnet_of(net) for net in result_networks):
            continue
        
        new_result_networks = []
        
        # Process each network in our current result list
        for network in result_networks:
            # If the subnet to subtract doesn't overlap with this network, keep it
            if not network.overlaps(subtract_net):
                new_result_networks.append(network)
                continue
            
            # If the subnet to subtract completely contains this network, skip it
            if subtract_net.subnet_of(network) and subtract_net.prefixlen == network.prefixlen:
                continue
            
            # Otherwise, get the address ranges that remain after subtraction
            new_result_networks.extend(
                ipaddress.IPv4Network(str(n)) 
                for n in ipaddress.collapse_addresses(
                    set(network.address_exclude(subtract_net))
                )
            )
        
        result_networks = new_result_networks
    
    # Summarize the remaining networks
    return sorted(ipaddress.collapse_addresses(result_networks))

def main():
    # Check if correct number of arguments was provided
    if len(sys.argv) < 2:
        print("Usage: python myapp.py <parent_network> [networks_to_subtract...]")
        sys.exit(1)
    
    try:
        parent_network = sys.argv[1]
        networks_to_subtract = list()
        
        for nw in sys.argv[2:]:
            if "\n" in nw:
                for n in nw.split('\n'):
                    try:
                        test = ipaddress.ip_network(n)
                        if test:
                            networks_to_subtract.append(n)
                    except:
                        print(f"Error parsing network {n}")
        
        # Get the result networks
        result = subtract_networks(parent_network, networks_to_subtract)
        
        # Print each resulting network on a new line
        for network in result:
            print(str(network))
            
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
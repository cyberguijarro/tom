#!/usr/bin/python

import re
import os
import sys
import os.path
import ConfigParser
import getopt
import commands

# Settings

debug = 0
verbose = 0

# Classes

class Product:
    def __init__(self):
        self.name = ''
        self.path = ''
        self.command = ''

class Node:
    def __init__(self):
        self.name = ''
        self.requirements = []
        self.products = []

# RE parsers

directives = re.compile('@[a-zA-Z]\s*.*')
literal = re.compile('"[^"]*"')

# Functions

def osName():
    if os.name == 'posix':
        status, output = commands.getstatusoutput("uname -s")
        return output.lower()
    else:
        return os.name

def logDebug(message):
    if debug:
        print message

def logInfo(message):
    if verbose:
        print message

def logMessage(message):
    print message
    
def hasValidExtension(file):
    result = 0
    extensions = ['.c', '.cpp', '.h', '.hpp']
    
    for extension in extensions:
        if (file.endswith(extension)):
            result = 1
            break
    
    return result

def completePath(base, file):
    return os.path.join(os.path.dirname(base), file)
    
def assignCommand(node, product, command):
    product.command = command;
    
    for variable in os.environ.iterkeys():
        product.command = product.command.replace('$' + variable, os.environ[variable])
    
    # $# source file
    # $~ source parent dir
    # $^ source requirements
    # $@ product name 
    product.command = product.command.replace('$#', node.name).replace('$~', os.path.dirname(node.name)).replace('$^', ' '.join(node.requirements)).replace('$@', product.name)

def scan(file):
    text = open(file).read()
    node = Node()
    node.name = file

    for directive in directives.findall(text):
        if directive.startswith('@requires'):
            for requirement in literal.findall(directive):
                node.requirements.append(completePath(file, requirement.strip('\"')))
        elif directive.startswith('@produces'):
            match = literal.search(directive)
            product = Product()
            product.name = match.group().strip('\"')
            product.path = completePath(file, product.name)
            assignCommand(node, product, directive[match.end() + 1:]) # Set command expanding variables
            node.products.append(product)

    logDebug ("Node %s (requires %s, %d products) registered." % (node.name, node.requirements, len(node.products)))

    return node

def build(target, products):
    built = 0

    if not target.startswith('.'):
        built += build(completePath('./', target), products)
    elif os.path.exists(target):
        if target in products:
            node = products[target]
            
            for requirement in node.requirements:
                built += build(requirement, products)
            
            # Rebuild if dependencies have been rebuilt or the source file changed
            if (built > 0) or (os.path.getmtime(target) < os.path.getmtime(node.name)):
                os.remove(target)
                built += build(target, products)
            else:
                print "%s is up-to-date." % target;
    elif target in products:
        node = products[target]

        for requirement in node.requirements:
            built += build(requirement, products)

        for product in node.products:
            if product.path == target:
                logMessage("Generating %s..." % product.name)
                logInfo(product.command)
                os.system(product.command)
                built += 1
                break        
    else:
        logMessage("Don't know how to build %s." % target)
    
    return built

# Main program

# Get command-line settings
(options, targets) = getopt.getopt(sys.argv[1:], 'vd')

if ('-v', '') in options:
    verbose = 1

if ('-d', '') in options:
    debug = 1

# Load environment variables from Tomfile
osid = osName()
logInfo("Operating system is %s." % osid)

config = ConfigParser.ConfigParser()    

if os.path.exists('Tomfile.' + osid):
    config.read(['Tomfile.' + osid])
elif os.path.exists('Tomfile'):
    config.read(['Tomfile'])

if (config.has_section('environment')):
    for name, value in config.items('environment'):
        logInfo("%s=%s" % (name.upper(), value))
        os.environ[name.upper()] = value

# Scan directory hierachy
products = dict()
for root, dirs, files in os.walk('.'):
    for file in files:
        if (hasValidExtension(file)):
            node = scan(os.path.join(root, file))
            for product in node.products:
                products[product.path] = node

# Execute defined action
if len(targets) == 0:
    targets.append('main') # default target

for target in targets:
    if target == 'help':
        logMessage("Listing available targets...")
        listed = []
        for node in products.itervalues():
            if node not in listed:
                for product in node.products:
                    print product.name
                listed.append(node)
    elif target == 'clean':
        for product in products.iterkeys():
            if os.path.exists(product):
                logMessage("Removing %s..." % product)
                os.remove(product)
    else:
        logMessage("Building %s..." % target)
        built = build(target, products)
        logMessage("Done (%d nodes built)." % built)
    
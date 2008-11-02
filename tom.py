#!/usr/bin/python
# @produces "install" TARGET='/usr/local/bin' && cp $# $TARGET/tom && chmod a+x $TARGET/tom && echo "Installed in $TARGET."

import re
import os
import sys
import os.path
import ConfigParser
import getopt
import commands
import threading
import mimetypes

# Settings

debug = 0
verbose = 0
defaultTargets = []
availableThreads = threading.Semaphore(1) # default thread count

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
        
class Builder(threading.Thread):
    def __init__(self, target, products):
        threading.Thread.__init__(self)
        self.target = target
        self.products = products
        self.built = 0
        self.start()

    def build(self, targets):
        builders = []
        built = 0
        
        for target in targets:
            thread = Builder(target, self.products)
            builders.append(thread)
        
        for builder in builders:
            builder.join()
            built += builder.built
        
        return built

    def run(self):
        try:
            built = 0
            target = self.target
            products = self.products

            if not target.startswith('.'):
                target = completePath('./', target)
            
            if os.path.exists(target):
                if target in products:
                    node = products[target]
                    built += self.build(node.requirements)
                    
                    # Rebuild if dependencies have been rebuilt or the source file changed
                    if (built > 0) or (os.path.getmtime(target) < os.path.getmtime(node.name)):
                        os.remove(target)
                        built += self.build([target])
                    else:
                        logMessage("%s is up-to-date." % target)
                        
            elif target in products:
                node = products[target]
                built += self.build(node.requirements)

                for product in node.products:
                    if product.path == target:
                        availableThreads.acquire()
                        logMessage("Generating %s..." % product.name)
                        logInfo(product.command)
                        os.system(product.command)
                        built += 1
                        availableThreads.release()
                        break
                        
            else:
                logMessage("Don't know how to build %s." % target)
            
            self.built = built
        except Exception, (message):
            print "Unexpected error while building %s: %s." % (self.target, message)
            
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
    
def getFileType(file):
    result = 'unknown'
    (type, encoding) = mimetypes.guess_type(file)
    
    if type != None:
        result = type.split('/')[0]
    
    return result;

def completePath(base, file):
    return os.path.join(os.path.dirname(base), file)
    
def assignCommand(node, product, command):
    product.command = command;
    path = os.path.dirname(node.name)
    changes = 1
    
    while changes > 0:
        changes = 0
        for variable in os.environ.iterkeys():
            target = '$' + variable
            if product.command.find(target) != -1:
                product.command = product.command.replace('$' + variable, os.environ[variable])
                changes = changes + 1
    
    # $# source file
    # $~ source parent dir
    # $^ source requirements
    # $@ product name 
    product.command = product.command.replace('$#', node.name).replace('$~', path).replace('$^', ' '.join(node.requirements)).replace('$@', os.path.join(path, product.name))

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
            if match != None:
                product = Product()
                product.name = match.group().strip('\"')
                product.path = completePath(file, product.name)
                assignCommand(node, product, directive[match.end() + 1:]) # Set command expanding variables
                node.products.append(product)
        elif directive.startswith('@default'):
            for target in literal.findall(directive):
                defaultTargets.append(target.strip('\"'))
            logInfo('Default targets are %s.' % defaultTargets)
            
    logDebug ("Node %s (requires %s, %d products) registered." % (node.name, node.requirements, len(node.products)))

    return node

def readEnvironment(file):
    config = ConfigParser.ConfigParser()
    config.read([file]);

    if (config.has_section('environment')):
        for name, value in config.items('environment'):
            logInfo("%s=%s" % (name.upper(), value))
            os.environ[name.upper()] = value


# Main program

try:
    # Get command-line settings
    (options, targets) = getopt.getopt(sys.argv[1:], 'vdt:')

    for (option, value) in options:
        if option == '-v':
            verbose = 1
        elif option == '-d':
            debug = 1
        elif option == '-t':
            availableThreads = threading.Semaphore(int(value))

    # Load environment variables from Tomfiles
    osid = osName()
    logInfo("Operating system is %s." % osid)

    directory = os.getcwd()
    tomfiles = []
    while (directory != '/'):
        filename = os.path.join(directory, 'Tomfile')

        if os.path.exists(filename + '.' + osid):
            tomfiles.insert(0, filename + '.' + osid)

        if os.path.exists(filename):
            tomfiles.insert(0, filename)

        directory = os.path.dirname(directory)

    for tomfile in tomfiles:
        logInfo("Reading environment variables from %s." % tomfile)
        readEnvironment(tomfile)

    # Scan directory hierachy
    products = dict()
    for root, dirs, files in os.walk('.'):
        for file in files:
            type = getFileType(file)
            if (type == 'text'):
                node = scan(os.path.join(root, file))
                for product in node.products:
                    products[product.path] = node
            else:
                logInfo('Skipping file %s (type "%s").' % (file, type))

    # Execute defined action
    if len(targets) == 0:
        for target in defaultTargets:
            targets.append(target)

    for target in targets:
        if target == 'help':
            logMessage("Available targets:")
            listed = []
            for node in products.itervalues():
                if node not in listed:
                    for product in node.products:
                        print "\t%s" % product.name
                    listed.append(node)
            logMessage("Default targets:")
            for target in defaultTargets:
                print "\t%s" % target
        elif target == 'clean':
            for product in products.iterkeys():
                if os.path.exists(product):
                    logMessage("Removing %s..." % product)
                    os.remove(product)
        else:
            logMessage("Building %s..." % target)
            builder = Builder(target, products)
            builder.join()
            logMessage("Done (%d nodes built)." % builder.built)
except Exception, (message):
    print "Unexpected error in main thread: %s." % message
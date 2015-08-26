#!/usr/bin/env python

"""
Copyright (c) 2010 Timothy J Fontaine <tjfontaine@atxconsulting.com>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

***
Discovery by DNS-SD: Copyright (c) 2013 Vidar Tysse <news@vidartysse.net>
***
"""

import os, optparse, re, urlparse
import os.path
from StringIO import StringIO

from xml.dom.minidom import parseString
from xml.dom import minidom

import sys

try:
    import lxml.etree as etree
    from lxml.etree import Element, ElementTree, tostring
except:
    try:
        from xml.etree.ElementTree import Element, ElementTree, tostring
        etree = None
    except:
        try:
            from elementtree import Element, ElementTree, tostring
            etree = None
        except:
            raise 'Failed to find python libxml or elementtree, please install one of those or use python >= 2.5'

try:
    import cups
except:
	cups = None

try:
	import avahisearch
except:
	avahisearch = None


XML_TEMPLATE = """<!DOCTYPE service-group SYSTEM "avahi-service.dtd">
<service-group>
<name replace-wildcards="yes"></name>
<service>
	<type>_ipp._tcp</type>
	<subtype>_universal._sub._ipp._tcp</subtype>
	<port>631</port>
	<txt-record>txtvers=1</txt-record>
	<txt-record>qtotal=1</txt-record>
	<txt-record>Transparent=T</txt-record>
	<txt-record>URF=DM3</txt-record>
</service>
</service-group>"""

#TODO XXX FIXME
#<txt-record>ty=AirPrint Ricoh Aficio MP 6000</txt-record>
#<txt-record>Binary=T</txt-record>
#<txt-record>Duplex=T</txt-record>
#<txt-record>Copies=T</txt-record>


DOCUMENT_TYPES = {
    # These content-types will be at the front of the list
    'application/pdf': True,
    'application/postscript': True,
    'application/vnd.cups-raster': True,
    'application/octet-stream': True,
    'image/urf': True,
    'image/png': True,
    'image/tiff': True,
    'image/png': True,
    'image/jpeg': True,
    'image/gif': True,
    'text/plain': True,
    'text/html': True,

    # These content-types will never be reported
    'image/x-xwindowdump': False,
    'image/x-xpixmap': False,
    'image/x-xbitmap': False,
    'image/x-sun-raster': False,
    'image/x-sgi-rgb': False,
    'image/x-portable-pixmap': False,
    'image/x-portable-graymap': False,
    'image/x-portable-bitmap': False,
    'image/x-portable-anymap': False,
    'application/x-shell': False,
    'application/x-perl': False,
    'application/x-csource': False,
    'application/x-cshell': False,
}

class AirPrintGenerate(object):
    def __init__(self, host=None, user=None, port=None, verbose=False,
        directory=None, prefix='AirPrint-', adminurl=False, usecups=True, 
        useavahi=False, dnsdomain=None):
        self.host = host
        self.user = user
        self.port = port
        self.verbose = verbose
        self.directory = directory
        self.prefix = prefix
        self.adminurl = adminurl
        self.usecups = usecups and cups
        self.useavahi = useavahi and avahisearch
        self.dnsdomain = dnsdomain
        
        if self.user:
            cups.setUser(self.user)
    
    def generate(self):
        collected_printers = list()

        # Collect shared printers from CUPS if applicable
        if self.usecups:
            if self.verbose:
                sys.stderr.write('Collecting shared printers from CUPS%s' % os.linesep)
            if not self.host:
                conn = cups.Connection()
            else:
                if not self.port:
                    self.port = 631
                conn = cups.Connection(self.host, self.port)
            
            printers = conn.getPrinters()
        
            for p, v in printers.items():
                if v['printer-is-shared']:
                    attrs = conn.getPrinterAttributes(p)
                    uri = urlparse.urlparse(v['printer-uri-supported'])

                    port_no = None
                    if hasattr(uri, 'port'):
                      port_no = uri.port
                    if not port_no:
                        port_no = self.port
                    if not port_no:
                        port_no = cups.getPort()

                    if hasattr(uri, 'path'):
                      rp = uri.path
                    else:
                      rp = uri[2]
                
                    re_match = re.match(r'^//(.*):(\d+)(/.*)', rp)
                    if re_match:
                      rp = re_match.group(3)
                
                    #Remove leading slashes from path
                    #TODO XXX FIXME I'm worried this will match broken urlparse
                    #results as well (for instance if they don't include a port)
                    #the xml would be malform'd either way
                    rp = re.sub(r'^/+', '', rp)
                
                    pdl = Element('txt-record')
                    fmts = []
                    defer = []

                    for a in attrs['document-format-supported']:
                        if a in DOCUMENT_TYPES:
                            if DOCUMENT_TYPES[a]:
                                fmts.append(a)
                        else:
                            defer.append(a)

                    if 'image/urf' not in fmts:
                        sys.stderr.write('image/urf is not in mime types, %s may not be available on ios6 (see https://github.com/tjfontaine/airprint-generate/issues/5)%s' % (p, os.linesep))

                    fmts = ','.join(fmts+defer)

                    dropped = []

                    # TODO XXX FIXME all fields should be checked for 255 limit
                    while len('pdl=%s' % (fmts)) >= 255:
                        (fmts, drop) = fmts.rsplit(',', 1)
                        dropped.append(drop)

                    if len(dropped) and self.verbose:
                        sys.stderr.write('%s Losing support for: %s%s' % (p, ','.join(dropped), os.linesep))

                    collected_printers.append( {
                        'SOURCE'    : 'CUPS', 
                        'name'      : p, 
                        'host'      : None,     # Could/should use self.host, but would break old behaviour
                        'address'   : None,
                        'port'      : port_no,
                        'domain'    : 'local', 
                        'txt'       : {
                            'txtvers'       : '1',
                            'qtotal'        : '1',
                            'Transparent'   : 'T',
                            'URF'           : 'none',
                            'rp'            : rp,
                            'note'          : v['printer-info'],
                            'product'       : '(GPL Ghostscript)',
                            'printer-state' : v['printer-state'],
                            'printer-type'  : v['printer-type'],
                            'adminurl'      : v['printer-uri-supported'],
                            'pdl'           : fmts,
                            }
                        } )
        
        # Collect networked printers using DNS-SD if applicable
        if (self.useavahi):
            if self.verbose:
                sys.stderr.write('Collecting networked printers using DNS-SD%s' % os.linesep)
            finder = avahisearch.AvahiPrinterFinder(verbose=self.verbose)
            for p in finder.Search():
                p['SOURCE'] = 'DNS-SD'
                collected_printers.append(p)
        
        # Produce a .service file for each printer found
        for p in collected_printers:
            self.produce_settings_file(p)

    def produce_settings_file(self, printer):
        printer_name = printer['name']
        
        tree = ElementTree()
        tree.parse(StringIO(XML_TEMPLATE.replace('\n', '').replace('\r', '').replace('\t', '')))

        name_node = tree.find('name')
        name_node.text = 'AirPrint %s @ %%h' % printer_name

        service_node = tree.find('service')

        port_node = service_node.find('port')
        port_node.text = '%d' % printer['port']
        
        host = printer['host']
        if host:
            if self.dnsdomain:
                pair = host.rsplit('.', 1)
                if len(pair) > 1:
                    host = '.'.join((pair[0], self.dnsdomain))
            service_node.append(self.new_node('host-name', host))

        txt = printer['txt']
        for key in txt:
            if self.adminurl or key != 'adminurl':
                service_node.append(self.new_txtrecord_node('%s=%s' % (key, txt[key])))

        source = printer['SOURCE'] if printer.has_key('SOURCE') else ''

        fname = '%s%s%s.service' % (self.prefix, '%s-' % source if len(source) > 0 else '', printer_name)
        
        if self.directory:
            fname = os.path.join(self.directory, fname)
        
        f = open(fname, 'w')

        if etree:
            tree.write(f, pretty_print=True, xml_declaration=True, encoding="UTF-8")
        else:
            xmlstr = tostring(tree.getroot())
            doc = parseString(xmlstr)
            dt= minidom.getDOMImplementation('').createDocumentType('service-group', None, 'avahi-service.dtd')
            doc.insertBefore(dt, doc.documentElement)
            doc.writexml(f)
        f.close()
        
        if self.verbose:
            src = source if len(source) > 0 else 'unknown'
            sys.stderr.write('Created from %s: %s%s' % (src, fname, os.linesep))

    def new_txtrecord_node(self, text):
        return self.new_node('txt-record', text)

    def new_node(self, tag, text):
        element = Element(tag)
        element.text = text
        return element


if __name__ == '__main__':
    parser = optparse.OptionParser()
    parser.add_option('-s', '--dnssd', action="store_true", dest="avahi",
        help="Search for network printers using DNS-SD (requires avahi)")
    parser.add_option('-D', '--dnsdomain', action="store", type="string",
        dest='dnsdomain', help='DNS domain where printers are located.',
        metavar='DNSDOMAIN')
    parser.add_option('-c', '--cups', action="store_true", dest="cups",
        help="Search CUPS for shared printers (requires CUPS)")
    parser.add_option('-H', '--host', action="store", type="string",
        dest='hostname', help='Hostname of CUPS server (optional)', metavar='HOSTNAME')
    parser.add_option('-P', '--port', action="store", type="int",
        dest='port', help='Port number of CUPS server', metavar='PORT')
    parser.add_option('-u', '--user', action="store", type="string",
        dest='username', help='Username to authenticate with against CUPS',
        metavar='USER')
    parser.add_option('-d', '--directory', action="store", type="string",
        dest='directory', help='Directory to create service files',
        metavar='DIRECTORY')
    parser.add_option('-v', '--verbose', action="store_true", dest="verbose",
        help="Print debugging information to STDERR")
    parser.add_option('-p', '--prefix', action="store", type="string",
        dest='prefix', help='Prefix all files with this string', metavar='PREFIX',
        default='AirPrint-')
    parser.add_option('-a', '--admin', action="store_true", dest="adminurl",
        help="Include the printer specified uri as the adminurl")
    
    (options, args) = parser.parse_args()
    
    if not (options.cups and cups) and not (options.avahi and avahisearch):
        sys.stderr.write('Nothing do do: --cups and/or --dnssd must be specified, and CUPS and/or avahi must be installed.%s' % os.linesep)
        os._exit(1)
    if options.cups and not cups:
        sys.stderr.write('Warning: CUPS is not available. Ignoring --cups option.%s' % os.linesep)
    if options.avahi and not avahisearch:
        sys.stderr.write('Warning: Module avahisearch is not available. Ignoring --dnssd option.%s' % os.linesep)
    
    if options.cups and cups:
        # TODO XXX FIXME -- if cups login required, need to add
        # air=username,password
        from getpass import getpass
        cups.setPasswordCB(getpass)
    
    if options.directory:
        if not os.path.exists(options.directory):
            os.mkdir(options.directory)
    
    apg = AirPrintGenerate(
        user=options.username,
        host=options.hostname,
        port=options.port,
        verbose=options.verbose,
        directory=options.directory,
        prefix=options.prefix,
        adminurl=options.adminurl,
        usecups=options.cups,
        useavahi=options.avahi,
        dnsdomain=options.dnsdomain,
    )
    
    apg.generate()

    if options.avahi and avahisearch and not options.dnsdomain:
        sys.stderr.write("NOTE: If a printer found by DNS-SD do not resolve outside the local subnet, specify the printers' DNS domain with --dnsdomain or edit the generated <host-name> element to fit your network.%s" % os.linesep)

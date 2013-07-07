#!/usr/bin/env python

"""
Search for printers that are announced over DNS-SD (aka Bonjour, Zeroconf, mDNS).

Use standalone to show DNS-SD printer properties.
Use as module to enumerate DNS-SD printers in your own code.

Used by a modified 'airprint-generate.py' to generate avahi .service files for
networked printers, allowing the printers to be announced on different subnets
by copying the .service files to /etc/avahi/services/ there.
This solves the problem of AirPrint printers not being availabe outside the
local subnet even though routing/NAT exists between subnets.

Copyright (c) 2013 Vidar Tysse <news@vidartysse.net>
Licence: Unlimited use is allowed. Including this copyright notice is requested.
"""

import optparse

import dbus, gobject, avahi
from dbus import DBusException
from dbus.mainloop.glib import DBusGMainLoop

class AvahiPrinterFinder(object):
    def __init__(self, ipv4_only=True, search_domain='local', verbose=False):
        self.search_protocol = avahi.PROTO_INET if ipv4_only else avahi.PROTO_UNSPEC
        self.search_domain = search_domain
        self.verbose = verbose
        self.service_type = '_ipp._tcp'  # Look for network printers
        self.still_receiving_events = 0
        self.printers = list()

    def ItemNew_handler(self, interface, protocol, name, stype, domain, flags):
        self.still_receiving_events = 1
        if self.verbose: print "Found service '%s' type '%s' domain '%s' " % (name, stype, domain)
        r_interface, r_protocol, r_name, r_stype, r_domain, r_host, r_aprotocol, r_address, r_port, r_txt, r_flags = \
            self.server.ResolveService(
                interface, protocol, name, stype, domain, 
                self.search_protocol, dbus.UInt32(0)
                )
        if self.verbose: print "RESOLVED: ", r_host, "-", r_name, "-", r_address, "-", r_port, "-", r_domain
        self.printers.append(
            dict(
                host        = str(r_host), 
                name        = str(r_name), 
                address     = str(r_address),
                port        = int(r_port),
                domain      = str(r_domain), 
                txt         = self.txtarray_to_dict(avahi.txt_array_to_string_array(r_txt))
                )
            )

    def AllForNow_handler(self):
        if self.verbose: print "Finishing on AllForNow."
        self.main_loop.quit()

    def timer_tick(self):
        if not self.still_receiving_events:
            if self.verbose: print "Finishing on timeout."
            self.main_loop.quit()
            return False;
        self.still_receiving_events = 0     # If still 0 on next call, we assume we're done
        return True
        
    def txtarray_to_dict(self, txtarray):
        txtdict = dict()
        for txt in txtarray:
            pair = txt.split('=', 1)
            txtdict[pair[0]] = '' if len(pair) < 2 else str(pair[1])
        return txtdict
        
    def Search(self):
        loop = DBusGMainLoop()

        bus = dbus.SystemBus(mainloop=loop)

        self.server = dbus.Interface( bus.get_object(avahi.DBUS_NAME, '/'),
                'org.freedesktop.Avahi.Server')

        sbrowser = dbus.Interface(bus.get_object(avahi.DBUS_NAME,
                self.server.ServiceBrowserNew(avahi.IF_UNSPEC,
                    self.search_protocol, self.service_type, self.search_domain, dbus.UInt32(0))),
                avahi.DBUS_INTERFACE_SERVICE_BROWSER)

        sbrowser.connect_to_signal("ItemNew", self.ItemNew_handler)
        sbrowser.connect_to_signal("AllForNow", self.AllForNow_handler)

        gobject.timeout_add(2000, self.timer_tick)

        self.main_loop = gobject.MainLoop()
        self.main_loop.run()
        return self.printers


if __name__ == '__main__':
    parser = optparse.OptionParser()
    parser.add_option('-v', '--verbose', action="store_true", dest="verbose",
        help="Print debugging information")
    (options, args) = parser.parse_args()

    finder = AvahiPrinterFinder(verbose=options.verbose)
    printers = finder.Search()
    for p in printers:
        print
        print p['name']
        print "  host       = %s" % p['host']
        print "  address    = %s" % p['address']
        print "  port       = %s" % p['port']
        print "  domain     = %s" % p['domain']
        print "  txt record:"
        for key in p['txt']:
            print "    %s = %s" % (key, p['txt'][key])
    print

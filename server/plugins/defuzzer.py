#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import calendar
import re
import shlex
import typing

"""
This is the query de-fuzzer library for Foal.
It turns a URL search query into an ES query

"""


def defuzz(formdata: dict, nodate: bool = False) -> dict:
    # Default to 30 day date range
    daterange = {"gt": "now-30d", "lt": "now+1d"}

    # Custom date range?
    # If a month is the only thing, fake start and end
    if "date" in formdata and "e" not in formdata:
        formdata["s"] = formdata["date"]
        formdata["e"] = formdata["date"]
    # classic start and end month params
    if "s" in formdata and "e" in formdata:
        syear, smonth = formdata["s"].split("-")
        eyear, emonth = formdata["e"].split("-")
        estart, eend = calendar.monthrange(int(eyear), int(emonth))
        daterange = {
            "gt": "%04u/%02u/01 00:00:00" % (int(syear), int(smonth)),
            "lt": "%04u/%02u/%02u 23:59:59" % (int(eyear), int(emonth), eend),
        }
    # Advanced date formatting
    elif "d" in formdata:
        # The more/less than N days/weeks/months/years ago
        m = re.match(r"^([a-z]+)=([0-9Mwyd]+)$", formdata["d"])
        if m:
            t = m.group(1)
            r = m.group(2)
            if t == "lte" and r:
                daterange = {"gt": "now-%s" % r}
            elif t == "gte" and r:
                daterange = {"lt": "now-%s" % r}
        # simple one month listing
        m = re.match(r"^(\d\d\d\d-\d+)$", formdata["d"])
        if m:
            xdate = m.group(1)
            dyear, dmonth = xdate.split("-", 1)
            daterange = {
                "gte": "%04u-%02u-01||/M" % (int(dyear), int(dmonth)),
                "lte": "%04u-%02u-01||/M" % (int(dyear), int(dmonth)),
                "format": "yyyy-MM-dd",
            }

        # dfr and dto defining a time span
        m = re.match(r"^dfr=(\d\d\d\d-\d+-\d+)\|dto=(\d\d\d\d-\d+-\d+)$", formdata["d"])
        if m:
            dfr = m.group(1)
            dto = m.group(2)
            syear, smonth, sday = dfr.split("-")
            eyear, emonth, eday = dto.split("-")
            daterange = {
                "gt": "%04u/%02u/%02u 00:00:00" % (int(syear), int(smonth), int(sday)),
                "lt": "%04u/%02u/%02u 23:59:59" % (int(eyear), int(emonth), int(eday)),
            }

    # List parameter(s)
    if "domain" in formdata:
        fqdn = formdata["domain"]
        listname = formdata.get("list", "*")
    elif "list" in formdata:
        listname, fqdn = formdata["list"].split("@", 1)
    else:  # No domain or list at all? BORK!
        listname = "*"
        fqdn = "*"
    list_raw = "<%s.%s>" % (listname, fqdn)

    # Default is to look in a specific list
    query_list_hash: typing.Dict = {"term": {"list_raw": list_raw}}

    # *@fqdn match?
    if listname == "*" and fqdn != "*":
        query_list_hash = {"wildcard": {"list_raw": {"value": "*.%s>" % fqdn}}}

    # listname@* match?
    if listname != "*" and fqdn == "*":
        query_list_hash = {"wildcard": {"list_raw": "<%s.*>" % listname}}

    # *@* ??
    if listname == "*" and fqdn == "*":
        query_list_hash = {"wildcard": {"list_raw": "*"}}

    must = [query_list_hash]
    must_not = []

    # Append date range if not excluded
    if not nodate:
        must.append({"range": {"date": daterange}})

    # Query string search:
    # - foo bar baz: find emails with these words
    # - orange -apples: fond email with oranges but not apples
    # - "this sentence": find emails with this exact string
    if "q" in formdata:
        qs = formdata["q"].replace(":", "")
        bits = shlex.split(qs)

        should = []
        shouldnot = []

        for bit in bits:
            force_positive = False
            # Translate -- into a positive '-', so you can find "-1" etc
            if bit[0:1] == "--":
                force_positive = True
                bit = bit[1:]
            # Negatives
            if bit[0] == "-" and not force_positive:
                # Quoted?
                if bit.find(" ") != -1:
                    bit = '"' + bit + '"'
                shouldnot.append(bit[1:])
            # Positives
            else:
                # Quoted?
                if bit.find(" ") != -1:
                    bit = '"' + bit + '"'
                should.append(bit)

        if len(should) > 0:
            must.append(
                {
                    "query_string": {
                        "fields": ["subject", "from", "body"],
                        "query": " AND ".join(should),
                    }
                }
            )
        if len(shouldnot) > 0:
            must_not.append(
                {
                    "query_string": {
                        "fields": ["subject", "from", "body"],
                        "query": " AND ".join(shouldnot),
                    }
                }
            )

    # Header parameters
    for header in ["from", "subject", "body", "to"]:
        hname = "header_%s" % header
        if hname in formdata:
            hvalue = formdata[hname]  # .replace('"', "")
            must.append({"match": {header: {"query": hvalue}}})

    thebool = {"must": must}

    if len(must_not) > 0:
        thebool["must_not"] = must_not

    return thebool

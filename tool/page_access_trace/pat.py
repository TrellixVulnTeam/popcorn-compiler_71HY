''' Parse page-access trace files for various analyses.  PAT files have a line
    for each page fault recorded by the operating system at a given moment in
    the application's execution.  Each line has the following format:

      0   1   2    3   4   5            6
    time nid tid perm ip addr <region | node bitmap>

    Where:
      time: timestamp of fault inside of application's execution
      nid : ID of node on which fault occurred
      tid: Linux task ID of faulting task
      perm: page access permissions (R/W/I)
      ip: instruction address which cause the fault
      addr: faulting memory address
      region: region identifier
      node bitmap: if perm = I, then this is a bitmask specifying to which
                   nodes invalidation messages were sent
'''

import os
import sys
from graph import Graph
from graph import InterferenceGraph

def getPage(addr):
    ''' Get the page for an address '''
    return addr & 0xfffffffffffff000

class ParseConfig:
    ''' Configuration for parsing a PAT file. Can be configuration to only
        parse entries within a given window and for certain types of accessed
        memory.
    '''
    def __init__(self, start, end, symbolTable, dwarfInfo,
                 noCode, noData, nodes, pages, regions):
        self.start = start
        self.end = end
        self.symbolTable = symbolTable
        self.dwarfInfo = dwarfInfo
        self.noCode = noCode
        self.noData = noData
        if nodes: self.nodes = set(nodes.split(','))
        else: self.nodes = None
        if pages: self.pages = set([int(x) for x in pages.split(',')])
        else: self.pages = None
        if regions: self.regions = set(regions.split(','))
        else: self.regions = None

def parsePAT(pat, config, callback, callbackData, verbose):
    ''' Generic parser.  For each line in the PAT file, determine if it fits
        the configuration.  If so, pass the parsed data to the callback.

        Note: we assume the entries in the PAT file are sorted by timestamp in
        increasing order.

        Arguments:
            pat (str): page access trace file
            config (ParseConfig): configuration for filtering PAT entries
            callback (func): callback function to analyze a single PAT entry
            callbackData (?): other data for the callback function
            verbose (bool): print verbose output
    '''
    if verbose: print("-> Parsing file '{}' <-".format(pat))

    with open(pat, 'r') as patfp:
        lineNum = 0
        for line in patfp:
            fields = line.split()

            # Filter based on a time window
            timestamp = float(fields[0])
            if timestamp < config.start: continue
            elif timestamp > config.end: break # No need to keep parsing

            # Filter based on node
            if config.nodes and fields[1] not in config.nodes: continue

            # Filter based on region
            if config.regions and fields[6] not in config.regions: continue

            addr = int(fields[5], base=16)

            # Filter based on page being accessed
            if config.pages and addr not in config.pages: continue

            # Filter based on type of memory object accessed
            if config.symbolTable:
                symbol = config.symbolTable.getSymbol(addr)
                if symbol:
                    if symbol.isCode() and config.noCode: continue
                    elif symbol.isData() and config.noData: continue
            else: symbol = None

            if verbose:
                lineNum += 1
                if lineNum % 10000 == 0:
                    sys.stdout.write("\rParsed {} faults...".format(lineNum))
                    sys.stdout.flush()

            callback(fields, timestamp, addr, symbol, callbackData)

    if verbose: print("\rParsed {} faults".format(lineNum))

def parsePATtoGraphs(pat, graphType, config, verbose):
    ''' Parse a page access trace (PAT) file and return graphs representing
        page fault patterns within a given time window.  Returns a graph per
        region contained in the PAT.

        Arguments:
            pat (str): page access trace file
            config (ParseConfig): configuration for filtering PAT entries
            verbose (bool): print verbose output

        Return:
            graphs (dict: int -> Graph): dictionary containing per-region
                                         thread/page access graph
    '''
    def graphCallback(fields, timestamp, addr, symbol, graphData):
        graphs = graphData[0]
        region = int(fields[6])
        tid = int(fields[2])
        if region not in graphs:
            if graphData[1] == "interference":
                graphs[region] = InterferenceGraph(graphData[2], True)
            else: graphs[region] = Graph(graphData[2], True)
        # TODO weight read/write accesses differently?
        graphs[region].addMapping(tid, getPage(addr))

    graphs = {}
    callbackData = (graphs, graphType, pat)
    parsePAT(pat, config, graphCallback, callbackData, verbose)

    if verbose: regions = ""
    for region in graphs:
        graphs[region].postProcess()
        if verbose: regions += "{} ".format(region)
    if verbose: print("Found {} regions: {}".format(len(graphs), regions[:-1]))

    return graphs

def parsePATtoTrendline(pat, config, numChunks, perthread, verbose):
    ''' Parse page fault into frequencies over the duration of the
        application's execution.  In order to graph frequencies, divide the
        execution into chunks.

        Note: in order to avoid extensive preprocessing, we assume the page
        faults are sorted by timestamp in the PAT file.

        Arguments:
            pat (str): page access trace file
            config (ParseConfig): configuration for filtering PAT entries
            numChunks (int): number of chunks into which to divide execution
            perthread (bool): maintain fault frequencies per thread
            verbose (bool): print verbose output

        Return:
            chunks (list:int): list of page faults within a chunk
            ranges (list:float): upper time bound of each chunk

        Return (per-thread):
            chunks (dict: int -> list:int): per-thread page faults within a
                                            chunk
            ranges (list:float): upper time bound of each chunk
    '''
    def getTimeRange(pat):
        with open(pat, 'rb') as fp:
            start = float(fp.readline().split(maxsplit=1)[0])
            fp.seek(-2, os.SEEK_END)
            while fp.read(1) != b"\n": fp.seek(-2, os.SEEK_CUR)
            end = float(fp.readline().split(maxsplit=1)[0])
            return start, end

    def trendlineCallback(fields, timestamp, addr, symbol, chunkData):
        ''' Add entry to chunk bucket based on the timestamp & PID. '''
        chunks = chunkData[0]
        ranges = chunkData[1]
        curChunk = chunkData[2]

        # Move to the next chunk if the timestamp is past the upper bound of
        # the current chunk.
        while timestamp > ranges[curChunk]: curChunk += 1
        chunkData[2] = curChunk # Need to maintain across callbacks!

        if perthread:
            tid = int(fields[2])
            if tid not in chunks: chunks[tid] = [ 0 for i in range(numChunks) ]
            chunks[tid][curChunk] += 1
        else: chunks[curChunk] += 1

    start, end = getTimeRange(pat)
    chunkSize = (end - start) / float(numChunks)
    assert chunkSize > 0.0, "Chunk size is too small, use fewer chunks"
    if verbose: print("-> Dividing application into {} {}s-sized chunks <-" \
                      .format(numChunks, chunkSize))

    if perthread: chunks = {}
    else: chunks = [ 0 for i in range(numChunks) ]
    ranges = [ (i + 1) * chunkSize + start for i in range(numChunks) ]
    ranges[-1] = ranges[-1] * 1.0001 # Avoid boundary corner cases caused by FP
                                     # representation for last entry
    callbackData = [ chunks, ranges, 0 ]
    parsePAT(pat, config, trendlineCallback, callbackData, verbose)

    # Prune chunks outside of the time window.  Include chunk if at least part
    # of it is contained inside the window.
    # TODO this should be directly calculated, but we have to specially handle
    # when the user doesn't set the window start/end times
    startChunk = 0
    endChunk = numChunks - 1
    for i in reversed(range(numChunks)):
        if ranges[i] >= config.start: startChunk = i
        else: break
    for i in range(numChunks):
        if ranges[i] <= config.end: endChunk = i
        else: break

    # Note: end number for python slices are not inclusive, but we want to
    # include endChunk so add 1
    endChunk += 1
    if perthread:
        retChunks = {}
        for tid in chunks: retChunks[tid] = chunks[tid][startChunk:endChunk]
        return retChunks, ranges[startChunk:endChunk]
    else: return chunks[startChunk:endChunk], ranges[startChunk:endChunk]

def getNumInvalidateMessages(bitmask):
    num = 0
    while bitmask > 0:
        num += bitmask & 1
        bitmask >>= 1
    return num

def parsePATforProblemSymbols(pat, config, verbose):
    ''' Parse PAT for symbols which cause the most faults.  Return a list of
        symbols sorted by the highest number of faults.

        Arguments:
            pat (str): page access trace file
            config (ParseConfig): configuration for filtering PAT entries
            verbose (bool): print verbose output

        Return:
            sortedSyms (list:tup(string, int)): list of symbols sorted by how
                                                often they're accessed, in
                                                descending order
    '''

    def problemSymbolCallback(fields, timestamp, addr, symbol, objAccessed):
        if fields[3] == "R":
            idx = 0
            amount = 1
        elif fields[3] == "W":
            idx = 1
            amount = 1
        else:
            idx = 2
            amount = getNumInvalidateMessages(int(fields[6]))

        if symbol:
            if symbol.name not in objAccessed:
                objAccessed[symbol.name] = [0, 0, 0]
            objAccessed[symbol.name][idx] += amount
        else:
            # TODO this is only an approximation!
            if addr > 0x7f0000000000: objAccessed["stack/mmap"][idx] += amount
            else: objAccessed["heap"][idx] += amount

    objAccessed = { "stack/mmap" : [0, 0, 0], "heap" : [0, 0, 0] }
    parsePAT(pat, config, problemSymbolCallback, objAccessed, verbose)

    # Generate list sorted by number of times accessed
    tuples = [ (tup[0], sum(tup[1]), tup[1]) for tup in objAccessed.items() ]
    return sorted(tuples, reverse=True, key=lambda s: s[1])

def parsePATforFaultLocs(pat, config, verbose):
    ''' Parse PAT for locations which cause the most faults.  Return a list of
        locations sorted by the highest number of faults.

        Arguments:
            pat (str): page access trace file
            config (ParseConfig): configuration for filtering PAT entries
            verbose (bool): print verbose output

        Return:
            allLocs (list:tup(string, int)): list of locations sorted by how
                                             many times a page fault occurred
                                             at that location
    '''
    def faultLocCallback(fields, timestamp, addr, symbol, locData):
        if fields[3] == "R":
            idx = 0
            amount = 1
        elif fields[3] == "W":
            idx = 1
            amount = 1
        else:
            idx = 2
            amount = getNumInvalidateMessages(int(fields[6]))

        dwarfInfo = locData[1]
        filename, linenum = dwarfInfo.getFileAndLine(int(fields[4], base=16))
        if filename:
            locs = locData[0]
            if filename not in locs: locs[filename] = { linenum : [0, 0, 0] }
            elif linenum not in locs[filename]:
                locs[filename][linenum] = [0, 0, 0]
            locs[filename][linenum][idx] += amount
        else: locData[0]["unknown"][idx] += amount

    def stringifyLoc(filename, linenum):
        return "{}:{}".format(filename, linenum)

    locs = { "unknown" : [0, 0, 0] }
    callbackData = (locs, config.dwarfInfo)
    parsePAT(pat, config, faultLocCallback, callbackData, verbose)

    # Generate list sorted by number of times accessed
    allLocs = []
    for name in locs:
        if name != "unknown":
            for line in locs[name]:
                allLocs.append((stringifyLoc(name, line),
                                sum(locs[name][line]),
                                locs[name][line]))
        else:
            allLocs.append((name, sum(locs[name]), locs[name]))
    allLocs.sort(reverse=True, key=lambda l: l[1])
    return allLocs

def parsePATforFalseSharing(pat, config, verbose):
    ''' Parse PAT for symbols which induce false sharing, i.e., two symbols
        on the same page accessed by threads on multiple nodes with R/W or
        W/W permissions.

        Arguments:
            pat (str): page access trace file
            config (ParseConfig): configuration for filtering PAT entries
            verbose (bool): print verbose output
    '''

    class PageTracker:
        ''' Logically track accesses to a page, including faults caused by
            false sharing.  False sharing is, by definition, caused when
            faults are induced by accessing separate program objects mapped to
            the same page.

            This implementation is heavily dependent on the fact we're using an
            MSI protocol and is only applicable for PATs from distributed
            execution.
        '''
        def __init__(self, page):
            self.page = page
            self.faults = 0
            self.falseFaults = 0
            self.seen = set([0])
            self.hasCopy = set([0])
            self.lastWrite = None
            self.problemSymbols = set()

        def track(self, symbol, nid, perm):
            ''' Track whether this fault is due to false sharing '''
            self.faults += 1

            # The first page access is not considered false sharing, as the
            # first fault happens regardless of any consistency protocol (we
            # have to transport the data over at least once!)
            if nid not in self.seen:
                self.seen.add(nid)
                return

            if perm == "W":
                # Either we're upgrading an existing page's permissions from
                # "R", or we're in an invalid state due to a previous write.
                # If the latter, check if the write was to the same symbol.
                if nid not in self.hasCopy and \
                        self.lastWrite and symbol != self.lastWrite:
                    self.problemSymbols.add(symbol)
                    self.problemSymbols.add(self.lastWrite)
                    self.falseFaults += 1
                self.hasCopy = set([nid])
                self.lastWrite = symbol
            else: # perm == "R"
                # We're in the invalid state due to a previous write (we never
                # need to "downgrade" permissions).  Check if was to the same
                # symbol.
                if self.lastWrite and symbol != self.lastWrite:
                    self.problemSymbols.add(symbol)
                    self.problemSymbols.add(self.lastWrite)
                    self.falseFaults += 1
                self.hasCopy.add(nid)

    def falseSharingCallback(fields, timestamp, addr, symbol, pagesAccessed):
        # Note: we can only track symbol table values, as we don't know the
        # semantics of the stack/heap/mapped memory
        if symbol:
            page = getPage(addr)
            if page not in pagesAccessed: pagesAccessed[page] = PageTracker(page)
            pagesAccessed[page].track(symbol.name, int(fields[1]), fields[3])

    pagesAccessed = {}
    parsePAT(pat, config, falseSharingCallback, pagesAccessed, verbose)

    return sorted(pagesAccessed.values(),
                  reverse=True,
                  key=lambda p: p.falseFaults)

def parsePATforPageFaultAtLoc(pat, config, loc, verbose):
    def pagesAtLocCallback(fields, timestamp, addr, symbol, pageData):
        dwarfInfo = pageData[0]
        filename, linenum = dwarfInfo.getFileAndLine(int(fields[4], base=16))
        if filename == pageData[2] and linenum == pageData[3]:
            if addr not in pageData[1]: pageData[1][addr] = 1
            else: pageData[1][addr] += 1
            pageData[4] += 1

    assert config.dwarfInfo, "No DWARF information for binary!"
    locSplit = loc.strip().split(":")
    assert len(locSplit) == 2, \
        "Invalid location '{}', must be 'file:line'".format(loc)
    pages = {}
    callbackData = [config.dwarfInfo, pages, locSplit[0], int(locSplit[1]), 0]
    parsePAT(pat, config, pagesAtLocCallback, callbackData, verbose)

    return sorted(pages.items(),
                  reverse=True,
                  key=lambda p: p[1]), callbackData[4]


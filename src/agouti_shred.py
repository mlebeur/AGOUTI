import os
import sys
import itertools
import re
import time
import collections

from lib import agouti_log as agLOG
from src import agouti_sequence as agSeq
from src import agouti_denoise as agDenoise

def get_attributes(attribute):
	dAttributes = {}
	tmp_attributes = attribute.split(';')
	for i in range(len(tmp_attributes)):
		tmp_attribute = tmp_attributes[i].split('=')
		attributeName = tmp_attribute[0]
		attributeValue = tmp_attribute[1]
		if attributeName not in dAttributes:
			dAttributes[attributeName] = attributeValue

	return dAttributes

def shred_annotation(dHeader2Intervals, gffFile, prefix, breakerProgress):
	breakerProgress.logger.info("[BEGIN] Shredding annotation")
	outGFF = prefix + ".shred.gff"
	fOUT = open(outGFF, 'w')
	annotationType = ["gene", "exon", "CDS", "five_prime_UTR", "three_prime_UTR"]
	n = 1
	preGene = ""
	preStrand = ""
	preSource = ""
	preHeader = ""
	preStart = 0
	preStop = 0
	dAttributes = {}
	features = []
	dFeatures = collections.defaultdict(list)
	nGenes = 0
	with open(gffFile, 'r') as fGFF:
		for line in fGFF:
			if line.startswith("##FASTA"):
				break
			if not line.startswith("#"):
				tmp_line = line.strip().split("\t")
				header = tmp_line[0]
				if header in dHeader2Intervals:
					intervals = dHeader2Intervals[header]
					# no cut
					if len(intervals) == 1:
						if tmp_line[2] in annotationType:
							fOUT.write(line)
							if tmp_line[2] == "gene":
								nGenes += 1
					# get cut
					else:
						start = int(tmp_line[3])
						stop = int(tmp_line[4])
						if tmp_line[2] == "gene":
							nGenes += 1
							dAttributes = get_attributes(tmp_line[8])
							if "ID" in dAttributes:
								gene = dAttributes["ID"]
							else:
								print "warning no gene ID extracted from attribute"
								gene = "agouti_shred_gene_%d" %(n)
								n += 1
							strand = tmp_line[6]
							source = tmp_line[1]
							if preGene == "":
								preGene = gene
								preStart = start
								preStop = stop
								preStrand = strand
								preSource = source
								preHeader = header
							else:
								if preGene != gene:
									print "preGene", preGene, "gene", gene
									shreds = []
									for i in range(len(intervals)):
										interval = intervals[i]
										overlap = agDenoise.find_overlap(interval, (preStart, preStop))
										if overlap == 0:
											print "start", preStart, "stop", preStop, "interval", interval, "index", i
											shreds += [(i, interval[0]+1, interval[1]+1)]
									print "shreds", shreds
									shred_gene(shreds, preGene, preStart, preStop,
											   preStrand, preSource, preHeader,
											   features, dFeatures, dAttributes, fOUT)
									preGene = gene
									preStart = start
									preStop = stop
									preStrand = strand
									preSource = source
									preHeader = header
									dFeatures = {k:[] for k in features}
									features = []
						elif tmp_line[2] == "exon":
							if not "exon" in features:
								features.append("exon")
								dFeatures["exon"] = [(start, stop)]
							else:
								dFeatures["exon"] += [(start, stop)]
						elif tmp_line[2] == "CDS":
							if "CDS" not in features:
								dFeatures["CDS"] = [(start, stop)]
								features.append("CDS")
							else:
								dFeatures["CDS"] += [(start, stop)]
						elif tmp_line[2] == "five_prime_UTR":
							if not "five_prime_UTR" in features:
								features.append("five_prime_UTR")
								dFeatures["five_prime_UTR"] = [(start, stop)]
							else:
								dFeatures["five_prime_UTR"] += [(start, stop)]
						elif tmp_line[2] == "three_prime_UTR":
							if not "three_prime_UTR" in features:
								features.append("three_prime_UTR")
								dFeatures["three_prime_UTR"] = [(start, stop)]
							else:
								dFeatures["three_prime_UTR"] += [(start, stop)]
			else:
				if line.startswith("##gff"):
					fOUT.write(line)
				elif not line.startswith("##"):
					fOUT.write(line)
		print "last", "preGene", preGene
		shreds = []
		for i in range(len(intervals)):
			interval = intervals[i]
			overlap = agDenoise.find_overlap(interval, (preStart, preStop))
			if overlap == 0:
				print "start", preStart, "stop", preStop, "interval", interval, "index", i
				shreds += [(i, interval[0]+1, interval[1]+1)]
		print "shreds", shreds
		shred_gene(shreds, preGene, preStart, preStop,
				   preStrand, preSource, preHeader,
				   features, dFeatures,
				   dAttributes, fOUT)

	print nGenes
	fOUT.close()

def shred_gene(shreds, preGene, preStart, preStop,
			   preStrand, preSource, preHeader,
			   features, dFeatures,
			   dAttributes, fOUT):
	shredGeneStart = 0
	shredGeneStop = 0
	shredExonStart = 0
	shredExonStop = 0
	shredCodStart = 0
	shredCodStop = 0
	offset1 = 0
	offset2 = 0
	dOffsets = {f:0 for f in features}
	for i in range(len(shreds)):
		index, shredStart, shredStop = shreds[i]
		print index, shredStart, shredStop
		if preStart > shredStart:
			shredGeneStart = preStart - shredStart + 1
			if preStop > shredStop:
				shredGeneStop = shredStop - shredStart + 1
			else:
				shredGeneStop = preStop - shredStart + 1
		elif preStart < shredStart:
			shredGeneStart = 1
			if preStop > shredStop:
				shredGeneStop = shredStop-shredStart+1
			else:
				shredGeneStop = preStop - shredStart + 1
		fOUT.write("%s_%d\t%s\tgene\t%d\t%d\t.\t%s\t.\t%s;%s\n"
				   %(preHeader, index, preSource, shredGeneStart,
				   shredGeneStop, preStrand, "ID=%s_%d" %(preGene, i),
				   ";".join(["%s=%s" %(k, v) for k,v in dAttributes.iteritems() if k != "ID"])))
		print features
		for f in features:
			offset = dOffsets[f]
			print "handle feature", f, "offset", offset
			featCoords = sorted(dFeatures[f])
			print "dFeatures", featCoords
			for j in range(offset, len(featCoords)):
				featStart = featCoords[j][0]
				featStop = featCoords[j][1]
				shredInfo = shred_features(shredStart, shredStop,
										   featStart, featStop)
				if shredInfo == 2:
					dOffsets[f] = j
					print "move to next", "offset", dOffsets[f], "feature", f
					break
				elif shredInfo == 3:
					continue
				else:
					shredExonStart = shredInfo[1]
					shredExonStop = shredInfo[2]
					fOUT.write("%s_%d\t%s\t%s\t%d\t%d\t.\t%s\t.\t%s\n"
							   %(preHeader, index, f, preSource, shredExonStart,
							   shredExonStop, preStrand,
							   "Parent=%s_%d" %(preGene, i)))

def shred_features(shredStart, shredStop,
				   featStart, featStop):
	print featStart, featStop, shredStart, shredStop
	shredFeatStart = 0
	shredFeatStop = 0
	if featStart > shredStop:
		return 2
	if featStop < shredStart:
		return 3
	if featStart > shredStart:
		shredFeatStart = featStart - shredStart + 1
		if featStop <= shredStop:
			shredFeatStop = featStop - shredStart + 1
		else:
			shredFeatStop = shredStop - shredStart + 1
	elif featStart < shredStart:
		print "feature interrupted, possible frame change"
		shredFeatStart = 1
		if featStop <= shredStop:
			shredFeatStop = featStop - shredStart + 1
		else:
			shredFeatStop = shredStop - shredStart + 1
	return 1, shredFeatStart, shredFeatStop

def agouti_shred_main(assemblyFile, gffFile, prefix,
					  minGaps, minCtgLen):
	breakerProgress = agLOG.PROGRESS_METER("SHREDDER")
	breakerProgress.logger.info("[BEGIN] Shredding assembly")
	outdir = os.path.dirname(os.path.realpath(prefix))
	if not os.path.exists(outdir):
		os.makedirs(outdir)
	dHeader2Intervals = shred_assembly(assemblyFile, breakerProgress, prefix, minGaps, minCtgLen)
	if gffFile:
		shred_annotation(dHeader2Intervals, gffFile, prefix, breakerProgress)

def shred_assembly(assemblyFile, breakerProgress, prefix, minGaps, minCtgLen):
	'''
		shred assembly at gaps of a minimum length
	'''
	outDebugFile = prefix + ".shred.debug"
	breakDebug = agLOG.DEBUG("SHREDDER", outDebugFile)
	outFa = prefix + ".ctg.fasta"
	outInfo = prefix +".shred.info.txt"
	dHeader2Intervals = collections.defaultdict(list)
	with open(outFa, 'w') as fOUTFA, open(outInfo, 'w') as fINFO:
		genomeSize = 0
		splitSize = 0
		numContigs = 0
		contigLens = []
		nSeqs = 0
		startTime = time.time()
		breakerProgress.logger.info("# processed\t| Current sequence ID\t| Elapsed Time")
		for header, seq in agSeq.read_fasta(assemblyFile):
			nSeqs += 1
			breakDebug.debugger.debug(">%s" %(header))
			genomeSize += len(seq)
			gapIndices = [(m.start(), m.end()-1) for m in re.finditer("[N|n]{%d,}" %(minGaps), seq)]
#			print gapIndices
#			print seq[gapIndices[0][0]:gapIndices[0][1]]
#			print seq[gapIndices[0][0]-5:gapIndices[0][0]]
#			sys.exit()
			gapIndices.append((len(seq), -1))
			breakDebug.debugger.debug("gapIndices: %s" %(str(gapIndices)))
			gapLens = []
			intervals = []
			if len(gapIndices) == 1:
				intervals.append((0, gapIndices[0][0]))
			elif gapIndices[-1][0] < minCtgLen:
				intervals.append((0, gapIndices[-1][0]))
			else:
				start = 0
				i = 0
				for i in range(len(gapIndices)):
					stop = gapIndices[i][0]
					breakDebug.debugger.debug("start %d stop %d" %(start, stop))
					if gapIndices[len(gapIndices)-1][0]-start < minCtgLen and \
					   len(gapIndices) > 1:
						breakDebug.debugger.debug("last short")
						breakDebug.debugger.debug("gapIndices[i]: %s" %(str(gapIndices[i])))
						breakDebug.debugger.debug("intervals: %s" %(intervals))
						#if len(intervals) > 0:
						intervals[-1] = (intervals[-1][0], gapIndices[len(gapIndices)-1][0])
						#else:
						#	intervals.append((start, gapIndices[len(gapIndices)-1][0]))
						break
					if stop-start+1 < minCtgLen:
						breakDebug.debugger.debug("short")
						breakDebug.debugger.debug("previous %s next %s" %(str(gapIndices[i-1]), str(gapIndices[i])))
						breakDebug.debugger.debug("length: %d" %(stop-start+1))
						continue
					if i < len(gapIndices)-1:
						gapLens.append(gapIndices[i][1]-gapIndices[i][0])
					intervals.append((start, stop))
					start = gapIndices[i][1]+1
			breakDebug.debugger.debug("intervals: %s" %(intervals))
			breakDebug.debugger.debug("gapLen: %s" %(str(gapLens)))
			contigs = []
			for i in range(len(intervals)):
				dHeader2Intervals[header] += [intervals[i]]
				start = intervals[i][0]
				stop = intervals[i][1]
				splitSize += (stop-start)
				contigID = "%s_%d" %(header, i)
				contigs.append(contigID)
				contigLens.append(stop-start)
				fOUTFA.write(">%s\n%s\n" %(contigID, seq[start:stop]))
			numContigs += len(contigs)
			if nSeqs % 10000 == 0:
				elapsedTime = float((time.time() - startTime)/60)
				breakerProgress.logger.info("%d processed\t| %s\t | %.2f m" %(nSeqs, header, elapsedTime))
			fINFO.write(">%s\n" %(header))
			if len(contigs) == 1:
				fINFO.write("%s\tNA\tNA\n" %(contigs[0]))
				continue
			for i in range(1, len(contigs)):
				fINFO.write("%s\t%s\t%d\n" %(contigs[i-1], contigs[i], gapLens[i-1]))
		if nSeqs < 10000:
			elapsedTime = float((time.time() - startTime)/60)
			breakerProgress.logger.info("%d processed\t| %s\t | %.2f m" %(nSeqs, header, elapsedTime))
		n50 = agSeq.get_assembly_NXX(contigLens)
		breakerProgress.logger.info("Total length of the given assembly: %d"
									%(genomeSize))
		breakerProgress.logger.info("Total length of the shred assembly: %d"
									%(splitSize))
		breakerProgress.logger.info("Number of sequences in the shred assembly: %d"
									%(numContigs))
		breakerProgress.logger.info("N50 of the shred assembly: %d" %(n50))
		return dHeader2Intervals
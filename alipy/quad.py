"""
Quads are asterisms of 4 stars, used to match the catalogs.
"""

import sys, os
import math
import numpy as np
import operator # For sorting
import copy
import itertools
import scipy.spatial

import star


class Quad:
	"""
	A geometric "hash", or asterism, as used in Astrometry.net :
	http://adsabs.harvard.edu/cgi-bin/bib_query?arXiv:0910.2233
	It is made out of 4 stars, and it is shift / scale / rotation invariant
	"""
	
	def __init__(self, fourstars):
		"""
		fourstars is a list of four stars
		
		We make the following attributes :
		self.hash
		self.stars (in the order A, B, C, D)
		
		"""
		assert len(fourstars) == 4
		
		tests = [(0,1), (0,2), (0,3), (1,2), (1,3), (2,3)]
		other = [(2,3), (1,3), (1,2), (0,3), (0,2), (0,1)]
		dists = np.array([fourstars[i].distance(fourstars[j]) for (i,j) in tests])
		assert np.min(dists) > 1.0

		maxindex = np.argmax(dists)
		(Ai, Bi) = tests[maxindex] # Indexes of stars A and B
		(Ci, Di) = other[maxindex] # Indexes of stars C and D
		A = fourstars[Ai]
		B = fourstars[Bi]
		C = fourstars[Ci]
		D = fourstars[Di]
		
		# We look for matrix transform [[a -b], [b a]] + [c d] that brings A and B to 00 11 :
		x = B.x - A.x
		y = B.y - A.y
		b = (x-y)/(x*x + y*y)
		a = (1.0/x) * (1.0 + b*y)
		c = b*A.y - a*A.x 
		d = - (b*A.x + a*A.y)
		
		t = star.SimpleTransform((a, b, c, d))
		
		# Test
		#print t.apply((A.x, A.y))
		#print t.apply((B.x, B.y))
		
		(xC, yC) = t.apply((C.x, C.y))
		(xD, yD) = t.apply((D.x, D.y))
		
		# Normal case
		self.hash = (xC, yC, xD, yD)
		
		# Break symmetries :
		testa = xC > xD
		testb = xC + xD > 1
		
		if testa and not testb: # we switch C and D
			#print "a"
			self.hash = (xD, yD, xC, yC)
			(C, D) = (D, C)
		
		if testb and not testa: # We switch A and B
			#print "b"
			self.hash = (1.0-xD, 1.0-yD, 1.0-xC, 1.0-yC)
			(A, B) = (B, A)
			(C, D) = (D, C)
			
		if testa and testb:
			#print "a + b"
			self.hash = (1.0-xC, 1.0-yC, 1.0-xD, 1.0-yD)
			(A, B) = (B, A)
	
		# Checks :
		assert self.hash[0] <= self.hash[2]
		assert self.hash[0] + self.hash[2] <= 1
		
		self.stars = [A, B, C, D] # Order might be different from the fourstars !
		
		
	def __str__(self):
		return "Hash : %6.3f %6.3f %6.3f %6.3f / IDs : (%s, %s, %s, %s)" % (
			self.hash[0], self.hash[1], self.hash[2], self.hash[3],
			self.stars[0].name, self.stars[1].name, self.stars[2].name, self.stars[3].name)


def mindist(fourstars):
	"""
	Function that tests if 4 stars are suitable to make a good quad...
	"""
	tests = [(0,1), (0,2), (0,3), (1,2), (1,3), (2,3)]
	dists = np.array([fourstars[i].distance(fourstars[j]) for (i,j) in tests])
	return np.min(dists)



def makequads1(starlist, n=7, verbose=True):
	"""
	First trivial quad maker.
	Makes combis of the n brightest stars.
	"""
	quadlist = []
	sortedstars = star.sortstarlistbyflux(starlist)

	for fourstars in itertools.combinations(sortedstars[:n], 4):
		if mindist(fourstars) > 50.0:
				quadlist.append(Quad(fourstars))	
	
	if verbose:
		print "Made %4i quads from %4i stars (combi n=%i)" % (len(quadlist), len(starlist), n)
		
	return quadlist



	
def makequads2(starlist, f=5.0, n=6, verbose=True):
	"""
	Similar, but fxf in subareas roughly f times smaller than the full frame.
	"""
	quadlist = []
	sortedstars = star.sortstarlistbyflux(starlist)
	(xmin, xmax, ymin, ymax) = star.area(sortedstars)
	
	r = 2.0 * max(xmax - xmin, ymax - ymin) / f
	
	for xc in np.linspace(xmin, xmax, f+2)[1:-1]:
		for yc in np.linspace(ymin, ymax, f+2)[1:-1]:
			cstar = star.Star(x=xc, y=yc)
			das = cstar.distanceandsort(sortedstars)
			#closest = [s["star"] for s in das[0:4]]
			brightestwithinr = star.sortstarlistbyflux([s["star"] for s in das if s["dist"] <= r])[:n]
			for fourstars in itertools.combinations(brightestwithinr, 4):
				if mindist(fourstars) > 20.0:
					quadlist.append(Quad(fourstars))
			
	if verbose:
		print "Made %4i quads from %4i stars (combi sub f=%.1f n=%i)" % (len(quadlist), len(starlist), f, n)

	return quadlist


def removeduplicates(quadlist, verbose=True):
	"""
	Returns a quadlist without quads with identical hashes...
	"""
	hasharray = np.array([q.hash for q in quadlist])
	
	order = np.lexsort(hasharray.T)
	hasharray = hasharray[order]
	#diff = np.diff(hasharray, axis=0)
	diff = np.fabs(np.diff(hasharray, axis=0))
	#diff = np.sum(diff, axis=1)
	ui = np.ones(len(hasharray), 'bool')
	ui[1:] = (diff >= 0.000001).any(axis=1)
	#print hasharray[ui==False]
	if verbose:
		print "Removing %i/%i duplicates" % (len(quadlist) - np.sum(ui), len(quadlist))
	
	return [quad for (quad, u) in zip(quadlist, ui) if u == True] 
	


def proposecands(uknquadlist, refquadlist, n=5):
	"""
	Function that identifies similar quads between the unknown image and a reference.
	"""

	uknhashs = np.array([q.hash for q in uknquadlist])	
	refhashs = np.array([q.hash for q in refquadlist])
	#print "Unknown quads   : ", uknhashs.shape[0]
	#print "Reference quads : ", refhashs.shape[0]
	
	# Brute force...
	dists = scipy.spatial.distance.cdist(refhashs, uknhashs)
	uknmindistindexes = np.argmin(dists, axis=0) # For each ukn, the index of the closest ref
	uknmindist = np.min(dists, axis=0) # The corresponding distances
	uknbestindexes = np.argsort(uknmindist)
	
	candlist = []
	for i in range(n):
		cand = [uknquadlist[uknbestindexes[i]], refquadlist[uknmindistindexes[uknbestindexes[i]]]]
		candlist.append(cand)
		#print uknmindist[uknbestindexes[i]]
	
	return candlist
	

def quadtrans(uknquad, refquad):
	"""
	Quickly return a transform estimated from the stars A and B of two quads.
	"""
	t = star.SimpleTransform()
	t.fitstars(uknquad.stars[:2], refquad.stars[:2])
	return t





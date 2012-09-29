"""
Overhaul of cosmouline's star module, for alipy2.
This module contains stuff for geometric matching algorithms.
"""

import sys, os
import math
import numpy as np
import operator # For sorting
import copy
import itertools
import scipy.linalg
import scipy.spatial




class Star:
	"""
	Simple class to represent a single source (usually stars, but not necessarily).
	In this module we often manipulate lists of such Star objects.
	"""

	def __init__(self, x=0.0, y=0.0, name="untitled", flux=-1.0, props={}, fwhm=-1.0, elon=-1.0):
		"""
		flux : Some "default" or "automatic" flux, might be a just good guess. Used for sorting etc.
		If you have several fluxes, colours, store them in the props dict.
		props : A placeholder dict to contain other properties of your choice (not required nor used by the methods).
		"""
		self.x = float(x)
		self.y = float(y)
		self.name = str(name)
		self.flux = float(flux)
		self.props = props
		self.fwhm = float(fwhm)
		self.elon = float(elon)
	
	def copy(self):
		return copy.deepcopy(self)
	
	def __getitem__(self, key) :
		"""
		Used for sorting list of stars.
		"""
		if key == 'flux':
			return self.flux
		if key == 'fwhm':
			return self.fwhm
		if key == 'elon':
			return self.elon
	
	def __str__(self):
		"""
		A string representation of a source.
		"""
		return "%10s : (%8.2f,%8.2f) | %12.2f | %5.2f %5.2f" % (self.name, self.x, self.y, self.flux, self.fwhm, self.elon)

	def coords(self):
		"""
		Returns the coords in form of an array.
		"""
		return np.array([self.x, self.y])

	def distance(self, otherstar):
		"""
		Returns the distance between the two stars.
		"""
		return math.sqrt(np.sum((self.coords() - otherstar.coords())**2))

	def trigangle(self, otherstar):
		"""
		returns the "trigonometric" angle of the vector that goes from
		self to the otherstar, in degrees
		"""
		return math.atan2(otherstar.y - self.y, otherstar.x - self.x) * (180.0/math.pi) % 360.0
		
	def distanceandsort(self, otherstarlist):
		"""
		Returns a list of dicts(star, dist, origpos), sorted by distance to self.
		The 0th star is the closest.
		
		otherstarlist is not modified.
		"""
		import operator # for the sorting
		
		returnlist=[]
		for i, star in enumerate(otherstarlist):
			dist = self.distance(star)
			returnlist.append({'star':star, 'dist':dist, 'origpos':i})
		returnlist = sorted(returnlist, key=operator.itemgetter('dist')) # sort stars according to dist
		
		return returnlist

### And now some functions to manipulate list of such stars ###


def printlist(starlist):
	"""
	Prints the stars ...
	"""
	for source in starlist:
		print source

def listtoarray(starlist):
	"""
	Transforms the starlist into a 2D numpy array for fast manipulations.
	First index is star, second index is x or y
	"""
	return np.array([star.coords() for star in starlist])
	
	
def area(starlist, border=0.01):
	"""
	Returns the area covered by the stars.
	Border is relative to max-min
	"""
	a = listtoarray(starlist)
	(xmin, xmax) = (np.min(a[:,0]), np.max(a[:,0]))
	(ymin, ymax) = (np.min(a[:,1]), np.max(a[:,1]))
	xw = xmax - xmin
	yw = ymax - ymin
	xmin = xmin - border*xw
	xmax = xmax + border*xw
	ymin = ymin - border*yw
	ymax = ymax + border*yw
	return np.array([xmin, xmax, ymin, ymax])
	

def readmancat(mancatfilepath, verbose="True"):
	"""
	Reads a "manual" star catalog -- by manual, I mean "not written by sextractor".
	So this is typically a *short* file.
	
	Comment lines start with #, blank lines are ignored.
	The format of a data line is
	
	starname xpos ypos [flux]
	
	The data is returned as a list of star objects.
	"""
	
	if not os.path.isfile(mancatfilepath):	
		print "File does not exist :"
		print mancatfilepath
		print "Line format to write : starname xpos ypos [flux]"
		sys.exit(1)
		
	
	myfile = open(mancatfilepath, "r")
	lines = myfile.readlines()
	myfile.close
	
	table=[]
	knownnames = [] # We check for uniqueness of the names
	
	for i, line in enumerate(lines):
		if line[0] == '#' or len(line) < 4:
			continue
		elements = line.split()
		nbelements = len(elements)
		
		if nbelements != 3 and nbelements != 4:
			print "Format error on line", i+1, "of :"
			print mancatfilepath
			print "The line looks like this :"
			print line
			print "... but we want : starname xpos ypos [flux]"
			sys.exit(1)
		
		name = elements[0]
		x = float(elements[1])
		y = float(elements[2])
		if nbelements == 4:
			flux = float(elements[3])
		else:
			flux = -1.0	
		
		if name in knownnames:
			print "Error in %s" % (mancatfilepath)
			print "The name '%s' (line %i) is already taken." % (name, i+1)
			print "This is insane, bye !"
			sys.exit(1)
		knownnames.append(name)
		
		#table.append({"name":name, "x":x, "y":y, "flux":flux})
		table.append(Star(x=x, y=y, name=name, flux=flux))
	

	if verbose: print "I've read", len(table), "sources from", os.path.split(mancatfilepath)[1]
	return table


def readsexcat(sexcat, verbose=True, maxflag = 2, posflux = True, propfields=[]):
	"""
	sexcat is either a string (path to a file), or directly an asciidata catalog object as returned by pysex
	
	We read a sextractor catalog with astroasciidata and return a list of stars.
	Minimal fields that must be present in the catalog :
		- NUMBER
		- X_IMAGE
		- Y_IMAGE
		- FWHM_IMAGE
		- ELONGATION
		- FLUX_AUTO
		- FLAGS
		
	maxflag : maximum value of the FLAGS that you still want to keep. Sources with higher values will be skipped.
	FLAGS == 0 : all is fine
	FLAGS == 2 : the flux is blended with another one; further info in the sextractor manual.
	
	posflux : if True, only stars with positive FLUX_AUTO are included.
	
	propfields : list of FIELD NAMES to be added to the props of the stars.
	
	I will always add FLAGS as a propfield by default.
	
	"""
	returnlist = []
	
	if isinstance(sexcat, str):
	
		import asciidata
		if not os.path.isfile(sexcat):
			print "Sextractor catalog does not exist :"
			print sexcat	
			sys.exit(1)
	
		if verbose : 
			print "Reading %s " % (os.path.split(sexcat)[1])
		mycat = asciidata.open(sexcat)
	
	else: # then it's already a asciidata object
		mycat = sexcat
		
	# We check for the presence of required fields :
	minimalfields = ["NUMBER", "X_IMAGE", "Y_IMAGE", "FWHM_IMAGE", "ELONGATION", "FLUX_AUTO", "FLAGS"]
	minimalfields.extend(propfields)
	availablefields = [col.colname for col in mycat]
	for field in minimalfields:
		if field not in availablefields:
			print "Field %s not available in your catalog file !" % (field)
			sys.exit(1)
	
	if verbose : 
		print "Number of sources in catalog : %i" % (mycat.nrows)
		
	propfields.append("FLAGS")
	propfields = list(set(propfields))
		
	if mycat.nrows == 0:
		if verbose :
			print "No stars in the catalog :-("
	else :
		for i, num in enumerate(mycat['NUMBER']) :
			if mycat['FLAGS'][i] > maxflag :
				continue
			flux = mycat['FLUX_AUTO'][i]
			if posflux and (flux < 0.0) :
				continue
			
			props = dict([[propfield, mycat[propfield][i]] for propfield in propfields])
			
			newstar = Star(x = mycat['X_IMAGE'][i], y = mycat['Y_IMAGE'][i], name = str(num), flux=flux,
					props = props, fwhm = mycat['FWHM_IMAGE'][i], elon = mycat['ELONGATION'][i])
			
			returnlist.append(newstar)
	
	if verbose:
		print "I've selected %i sources" % (len(returnlist))
		
	return returnlist

def findstar(starlist, nametofind):
	"""
	Returns a list of stars for which name == nametofind
	"""
	foundstars = []
	for source in starlist:
		if source.name == nametofind:
			foundstars.append(source)
	return foundstars

def sortstarlistbyflux(starlist):
	"""
	We sort starlist according to flux : highest flux first !
	"""
	sortedstarlist = sorted(starlist, key=operator.itemgetter('flux'))
	sortedstarlist.reverse()
	return sortedstarlist

def sortstarlistby(starlist, measure):
	"""
	We sort starlist according to measure : lowest first !
	Where measure is one of flux, fwhm, elon
	"""
	sortedstarlist = sorted(starlist, key=operator.itemgetter(measure))
	return sortedstarlist









class SimpleTransform:
	"""
	Represents an affine transformation consisting of rotation, isotropic scaling, and shift.
	[x', y'] = [[a -b], [b a]] * [x, y] + [c d]
	"""
	
	def __init__(self, v = (1, 0, 0, 0)):
		"""
		v = (a, b, c, d)
		"""
		self.v = np.asarray(v)
	
	def getscaling(self):
		return math.sqrt(self.v[0]*self.v[0] + self.v[1]*self.v[1])
		
	def getrotation(self):
		"""
		The CCW rotation angle, in degrees
		"""
		return math.atan2(self.v[1], self.v[0]) * (180.0/math.pi)# % 360.0
	
	def __str__(self):
		return "Rotation %+9.6f [deg], Scaling %8.6f" % (self.getrotation(), self.getscaling())
		
	
	def apply(self, (x, y)):
		xn = self.v[0]*x -self.v[1]*y + self.v[2]
		yn = self.v[1]*x +self.v[0]*y + self.v[3]
		return (xn, yn)
		
	def applystar(self, star):
		transstar = star.copy()
		(transstar.x, transstar.y) = self.apply((transstar.x, transstar.y))
		return transstar
	
	def applystarlist(self, starlist):
		return [self.applystar(star) for star in starlist]
	
	
	def fitstars(self, uknstars, refstars):
		"""
		I set the transform so that it puts the unknown stars (uknstars) onto the refstars.
		If you supply only two stars, this is using linalg.solve() -- perfect solution.
		If you supply more stars, we use linear least squares, i.e. minimize the 2D error.
		
		Formalism inspired by :
		http://math.stackexchange.com/questions/77462/
		"""
		
		assert len(uknstars) == len(refstars)
		
		# ukn * x = ref
		# x is the transform (a, b, c, d)
		
		ref = np.hstack(listtoarray(refstars)) # a 1D vector of lenth 2n
		
		uknlist = []
		for star in uknstars:
			uknlist.append([star.x, -star.y, 1, 0])
			uknlist.append([star.y, star.x, 0, 1])
		ukn = np.vstack(np.array(uknlist)) # a matrix
		
		if len(uknstars) == 2:
			trans = scipy.linalg.solve(ukn, ref)
		else:
			trans = scipy.linalg.lstsq(ukn, ref)[0]
		
		self.v = np.asarray(trans)


	def teststars(self, uknstars, refstars, refrad=2.0):
		"""
		We apply the trans to the uknstarlist, and check for correspondance with the refstarlist.
		Returns the number of uknstars that could be matched to refstars within refrad.
		"""
		
		transuknstars = self.applystarlist(uknstars)
		
		transukn = listtoarray(transuknstars)
		ref = listtoarray(refstars)
		#print "Unknown stars   : ", transukn.shape[0]
		#print "Reference stars : ", ref.shape[0]
		
		mindists = np.min(scipy.spatial.distance.cdist(ref, transukn), axis=0)
		nbmatch = np.sum(mindists < refrad)
		#print "Matching stars  : ", nbmatch
		
		return nbmatch
		
		
	def refinestars(self, uknstars, refstars, refrad=5.0):
		"""
		I refit myself to all matching stars.
		"""
		
		transuknstars = self.applystarlist(uknstars)
		transukn = listtoarray(transuknstars)
		ref = listtoarray(refstars)
		
		# Brute force...
		dists = scipy.spatial.distance.cdist(ref, transukn)
		uknmindistindexes = np.argmin(dists, axis=0) # For each ukn, the index of the closest ref
		uknmindist = np.min(dists, axis=0) # The corresponding distances
		uknkeepers = uknmindist < refrad
		
		matchuknstars = []
		matchrefstars = []
		for i in range(len(uknkeepers)):
			if uknkeepers[i] == True:
				matchuknstars.append(uknstars[i])
				matchrefstars.append(refstars[uknmindistindexes[i]])
	
		self.fitstars(matchuknstars, matchrefstars)




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
		
		t = SimpleTransform((a, b, c, d))
		
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
	Function that tests if these 4 stars are suitable to make a good quad...
	"""
	tests = [(0,1), (0,2), (0,3), (1,2), (1,3), (2,3)]
	dists = np.array([fourstars[i].distance(fourstars[j]) for (i,j) in tests])
	return np.min(dists)


def ccworder(a):
	"""
	Sorting a coordinate array CCW to plot polygons ...
	"""
	ac = a - np.mean(a, 0)
	indices = np.argsort(np.arctan2(ac[:, 1], ac[:, 0]))
	return a[indices]

	

def makequads(starlist, n=10, plot=False, verbose=True):
	"""
	Give me a list, I return a list of some quads. This is the magic kitchen recipe...
	"""

	quadlist = []
	sortedstars = sortstarlistbyflux(starlist)
	
	if verbose:
		print "Building quads for %i stars ..." % len(starlist)
	
	# We start by combis of the brightest ones :
	
	for fourstars in itertools.combinations(sortedstars[:8], 4):
		if mindist(fourstars) > 50.0:
				quadlist.append(Quad(fourstars))	
	
	
	# Bright quads in subareas :
	(xmin, xmax, ymin, ymax) = area(sortedstars)
	
	f = 3
	r = 1.5*max(xmax - xmin, ymax - ymin)/f
	for xc in np.linspace(xmin, xmax, f+2):
		for yc in np.linspace(ymin, ymax, f+2):
			cstar = Star(x=xc, y=yc)
			das = cstar.distanceandsort(sortedstars[:200])
			#closest = [s["star"] for s in das[0:4]]
			brightestwithinr = sortstarlistbyflux([s["star"] for s in das if s["dist"] <= r])[0:5]
			for fourstars in itertools.combinations(brightestwithinr, 4):
				if mindist(fourstars) > 10.0:
					quadlist.append(Quad(fourstars))
		
		
	f = 6
	r = 1.5*max(xmax - xmin, ymax - ymin)/f
	for xc in np.linspace(xmin, xmax, f+2):
		for yc in np.linspace(ymin, ymax, f+2):
			cstar = Star(x=xc, y=yc)
			das = cstar.distanceandsort(sortedstars[:200])
			#closest = [s["star"] for s in das[0:4]]
			brightestwithinr = sortstarlistbyflux([s["star"] for s in das if s["dist"] <= r])[0:5]
			for fourstars in itertools.combinations(brightestwithinr, 4):
				if mindist(fourstars) > 10.0:
					quadlist.append(Quad(fourstars))

	"""
	f = 12
	r = 2.0*max(xmax - xmin, ymax - ymin)/f
	for xc in np.linspace(xmin, xmax, f+2):
		for yc in np.linspace(ymin, ymax, f+2):
			cstar = Star(x=xc, y=yc)
			das = cstar.distanceandsort(sortedstars[:200])
			#closest = [s["star"] for s in das[0:4]]
			brightestwithinr = sortstarlistbyflux([s["star"] for s in das if s["dist"] <= r])[0:4]
			for fourstars in itertools.combinations(brightestwithinr, 4):
				if mindist(fourstars) > 10.0:
					quadlist.append(Quad(fourstars))
	"""
	
	
	if verbose:
		print "Done, %i quads" % (len(quadlist))

	if plot:
		import matplotlib.pyplot as plt
		import matplotlib.patches as patches
		from matplotlib.collections import PatchCollection
	
		a = listtoarray(starlist)
		plt.plot(a[:,0], a[:,1], marker=",", ls="none", color="black")
		ax = plt.gca()

		for quad in quadlist:
			polycorners = listtoarray(quad.stars)
			polycorners = ccworder(polycorners)
			plt.fill(polycorners[:,0], polycorners[:,1], alpha=0.1, ec="none")
	
		(xmin, xmax, ymin, ymax) = area(starlist)
		plt.xlim(xmin, xmax)
		plt.ylim(ymin, ymax)
		ax.set_aspect('equal', 'datalim')
		plt.show()
	
	return quadlist
	

def proposecands(uknquadlist, refquadlist, n=5):
	"""
	Function that identifies similar quads between the unknown image and a reference.
	"""

	uknhashs = np.array([quad.hash for quad in uknquadlist])	
	refhashs = np.array([quad.hash for quad in refquadlist])
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
	t = SimpleTransform()
	t.fitstars(uknquad.stars[:2], refquad.stars[:2])
	return t


























################################################################################################################################





def formpairs(starlist1, starlist2, tolerance = 2.0, onlysingle = False, transform = False, scalingratio = 1.0, angle = 0.0, shift = (0.0, 0.0), verbose = True):
	"""
	starlist1 and starlist2 are two lists of stars.
	For each star in starlist1, we find the closest star of starlist2, if found within a given tolerance.
	starlist1 = hand picked stars
	starlist2 = large catalog of 
	We return a list of pairs of the corresponding stars (in form of a dict). See first lines to get that.
	
	transform == True :
		starlist2 is tranformed, using scalingration, angle, and shift, prior to the pair creation.
		Nevertheless, the idlist 2 will be filled with the raw untransformed stars from starlist2 !!!
		
	
	tolerance = maximum distance between identified stars. Set it high -> simply select the closest one.
	onlysingle == False : closest star within tolerance
	onlysingle == True : same, but only if no other star is within tolerance
	
	"""
	idlist1 = [] # Stars of starlist1 identified in starlist2
	idlist2 = [] # The corresponding starlist2 stars (same number, same order)
	iddists = [] # The list of distances between the stars of idlist1 and idlist2 (same number and order)
	nomatch = [] # Stars of starlist1 that could not be identified in starlist2
	notsure = [] # Stars of starlist1 that could not doubtlessly be identified in starlist2
	
	
	# If required, we transform the starlist 2 :
	if transform :
		transtarlist2 = copy.deepcopy(starlist2)
		zoomstarlist(transtarlist2, scalingratio)
		rotatestarlist(transtarlist2, angle, (0, 0))
		shiftstarlist(transtarlist2, shift)
		# Remember : we will pick the stars to fill idlist2 from the raw starlist2 !
	
	else:
		transtarlist2 = starlist2
	
	returndict = {"idlist1":idlist1, "idlist2":idlist2, "iddists":iddists, "nomatch":nomatch, "notsure":notsure}
	
	if len(starlist1) == 0:
		if verbose :
			print "Your starlist1 is empty, nothing to do."
		return returndict
	
	if len(transtarlist2) == 0:
		if verbose :
			print "Your starlist2 is empty, no stars to identify."
		nomatch.extend(starlist1)
		return returndict
			
	# Special treatment in the case there is only one star in starlist2
	if len(transtarlist2) == 1:
		if verbose :
			print "Your starlist2 is quite small..."
		for handstar in starlist1:
			closest = handstar.distanceandsort(transtarlist2)
			if closest[0]['dist'] > tolerance:
				if verbose :
					print "No match for star %s" % handstar.name
				nomatch.append(handstar)
				continue
			else:
				idlist1.append(handstar)
				idlist2.append(starlist2[closest[0]['origpos']])
				iddists.append(closest[0]['dist'])
		
		return returndict
				
	# The usual case :
	else:	
		for handstar in starlist1:
			closest = handstar.distanceandsort(transtarlist2)
			if closest[0]['dist'] > tolerance:
				if verbose :
					print "No match for star %s" % handstar.name
				nomatch.append(handstar)
				continue
				
			# Ok, then it must be closer then tolerance. We check for other stars whose distance is less then tolerance different from the first ones distance :
			elif onlysingle and (closest[1]['dist'] - closest[0]['dist'] < tolerance):
				if verbose :
					print "Multiple candidates for star %s, skipping" % handstar.name
				notsure.append(handstar)
				continue
			
			# Finally, this means we have found our star
			else:
				idlist1.append(handstar)
				idlist2.append(starlist2[closest[0]['origpos']])
				iddists.append(closest[0]['dist'])
	
		return returndict
	


def listidentify(starlist1, starlist2, tolerance = 2.0, onlysingle = False, transform = False, scalingratio = 1.0, angle = 0.0, shift = (0.0, 0.0), verbose = True):
	"""
	Same as formpairs (we call it), but we return only the idlist2 (not transformed, even if you give a transform), but with names taken from idlist1.
	Typical : starlist2 is a sextractor catalog with random names, starlist 1 is a handpicked catalog with special names,
	and you want to get stars with sextractor properties but your own names.
	"""
	
	formpairsdict = formpairs(starlist1, starlist2, tolerance = tolerance, onlysingle = onlysingle, transform = transform, scalingratio = scalingratio, angle = angle, shift = shift, verbose = verbose)
	
	match = []
	
	for (s1, s2, d) in zip(formpairsdict["idlist1"], formpairsdict["idlist2"], formpairsdict["iddists"]):
		s2.name = s1.name
		s2.props["iddist"] = d
		match.append(s2)
		
	nomatchnames = [s.name for s in formpairsdict["nomatch"]]
	notsurenames = [s.name for s in formpairsdict["notsure"]]
	
	return {"match":match, "nomatchnames":nomatchnames, "notsurenames":notsurenames}

	


def findtrans(preciserefmanstars, autostars, scalingratio = 1.0, tolerance = 2.0, minnbrstars = 5, mindist = 100.0, nref = 10, nauto = 30, verbose=True):
	
	"""
	Finds a rotation and shift between two catalogs (a big dirty one and a small handpicked one).
	Both catalogs should be SORTED IN FLUX, and the second one should be smaller for max performance.
	
	Only the first nref stars of preciserefmanstars are considered for searching the possible matches, and furthermore only 
	pairs farther then mindist are considered.
	
	tolerance is used when looking if a match was found.
	
	minnbrstars = as soon as this number of stars are identified, the algo stops, we look no further.
	
	The scalingratio parameter is a float to multiply with a distance of the autostars to match the same distance between the preciserefmanstars.
	
	We return a dict of 3 things :
	- nbr of identified stars (-1 if failed)
	- rotation angle (center = 0,0)
	- shift
	
	This should then be used to transform your autostars, and then run listidentify between the catalogs if you want ...
	This is done with the function formpairs
	
	"""
	
	# Think of a Hubble expansion with "origin" (0,0)
	# We apply this to the image to align, so that it matches the distances in the reference image.
	autostarscopy = copy.deepcopy(autostars)
	zoomstarlist(autostarscopy, scalingratio)
	
	n = 0 # a counter for the number of tries
	indentlist = [] # only used in case of failure
	
	for b, brightstar in enumerate(preciserefmanstars[:nref]):
		for f, faintstar in enumerate(preciserefmanstars[:nref]):
			if f == b: continue
			stardistance = brightstar.distance(faintstar)
			if stardistance < mindist : continue
			
			# We have a pair of stars from the preciserefmancat.
			# Let's see if we find to stars in the autocat with a similar distance.
			
			for bc, brightcandidate in enumerate(autostarscopy[:nauto]):
				for fc, faintcandidate in enumerate(autostarscopy[:nauto]):
					if fc == bc: continue
					candidatedistance =  brightcandidate.distance(faintcandidate)
					if math.fabs(candidatedistance - stardistance)/stardistance > 0.05 :
						# So if there is a disagreement larger then 5 percent...
						continue
					
					# We now have a promising pair of pairs, let's check them out.
					
					n = n+1
					
					starangle = brightstar.trigangle(faintstar)
					candidateangle = brightcandidate.trigangle(faintcandidate)
					rotcandangle = (starangle - candidateangle) % 360.0	# value to "add" to cand to match the star
					
					# We apply this rotation to the bright candidate, to determine the shift :
					testcand = copy.deepcopy(brightcandidate)
					testcand.rotate(rotcandangle, (0, 0))
					candshift = testcand.findshift(brightstar)
					
					# We apply the rotation and this shift to the full zoomed autostarlist :
					testcandlist = copy.deepcopy(autostarscopy)
					rotatestarlist(testcandlist, rotcandangle, (0, 0))
					shiftstarlist(testcandlist, candshift)
					
					# We evaluate the match between the transformed autostars and the ref stars :
					
					pairsdict = formpairs(preciserefmanstars, testcandlist, tolerance = tolerance, onlysingle = True, verbose = False)
					nbrids = len(pairsdict["idlist1"])
					indentlist.append(nbrids)
					
					if nbrids >= minnbrstars:
						# We got it !
						
						if verbose :
							print "Number of tries : %i" % n
							print "Distance difference : %.2f pixels" % math.fabs(candidatedistance - stardistance)
							print "Candidate rotation angle : %.2f degrees" % rotcandangle
							
							print "Star pairs used :"
							print brightstar
							print faintstar
							print brightcandidate
							print faintcandidate
							
							print "Identified stars : %i / %i" % (nbrids, len(preciserefmanstars) )

						return {"nbrids":nbrids, "angle":rotcandangle, "shift":candshift}

	
	if verbose :
		print "I'm a superhero, but I failed"
	if len(indentlist) > 0:
		if verbose :
			print "Maximum identified stars : %i" % max(indentlist)
			
	return {"nbrids":-1, "angle":0.0, "shift":(0.0, 0.0)}
					


def writeforgeomap(filename, pairs):
	"""
	Writes an input catalog of corresponding star pairs, for geomap
	Pair is a list of couples like (refstar, startoalign)
	"""


	import csv
	
	table = []	
	for pair in pairs:
		table.append([pair[0].x, pair[0].y, pair[1].x, pair[1].y])

	geomap = open(filename, "wb") # b needed for csv
	writer = csv.writer(geomap, delimiter="\t")
	writer.writerows(table)
	geomap.close()


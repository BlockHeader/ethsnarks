"""
This module implements the extended twisted edwards and extended affine coordinates
described in the paper "Twisted Edwards Curves Revisited":

 - https://iacr.org/archive/asiacrypt2008/53500329/53500329.pdf
   Huseyin Hisil, Kenneth Koon-Ho Wong, Gary Carter, and Ed Dawson

		Information Security Institute,
		Queensland University of Technology, QLD, 4000, Australia
		{h.hisil, kk.wong, g.carter, e.dawson}@qut.edu.au

By using the extended coordinate system we can avoid expensive modular exponentiation
calls, for example - a scalar multiplication call (or multiple...) may perform only
one 3d->2d projection at the point where affine coordinates are necessary, and every
intermediate uses a much faster form.
"""

from hashlib import sha256
from collections import namedtuple

from .field import FQ, SNARK_SCALAR_FIELD
from .numbertheory import SquareRootError


JUBJUB_Q = SNARK_SCALAR_FIELD
JUBJUB_ORDER = 21888242871839275222246405745257275088614511777268538073601725287587578984328
JUBJUB_C = 8		# Cofactor
JUBJUB_L = JUBJUB_ORDER//JUBJUB_C
JUBJUB_A = 168700	# Coefficient A
JUBJUB_D = 168696	# Coefficient D


"""
From "Twisted Edwards Curves", 2008-BBJLP
Theorem 3.2
"""
MONT_A = 168698	# int(2*(JUBJUB_A+JUBJUB_D)/(JUBJUB_A-JUBJUB_D))
MONT_B = 1		# int(4/(JUBJUB_A-JUBJUB_D))
MONT_A24 = int((MONT_A+2)/4)
assert MONT_A24*4 == MONT_A+2


"""
2017-BL - "Montgomery curves and the Montgomery ladder"
- https://eprint.iacr.org/2017/293.pdf
4.3.5, The curve parameters satisfy:
"""
assert JUBJUB_A == (MONT_A+2)/MONT_B
assert JUBJUB_D == (MONT_A-2)/MONT_B


class AbstractCurveOps(object):
	def __neg__(self):
		return self.neg()

	def __add__(self, other):
		return self.add(other)

	def __sub__(self, other):
		return self.add(other.neg())

	def __mul__(self, n):
		return self.mult(n)

	def double(self):
		return self.add(self)

	def rescale(self):
		return self

	def is_negative(self):
		p = self.as_point()
		q = Point.from_y(p.y)
		return p.x == -q.x

	def sign(self):
		return 1 if self.is_negative() else 0

	def mult(self, scalar):
		if isinstance(scalar, FQ):
			if scalar.m not in [SNARK_SCALAR_FIELD, JUBJUB_ORDER, JUBJUB_L]:
				raise ValueError("Invalid field modulus")
			scalar = scalar.n
		p = self
		a = self.infinity()
		i = 0
		while scalar != 0:
			if (scalar & 1) != 0:
				a = a.add(p)
			p = p.double()
			scalar = scalar // 2
			i += 1
		return a


class Point(AbstractCurveOps, namedtuple('_Point', ('x', 'y'))):
	@classmethod
	def from_y(cls, y):
		"""
		x^2 = (y^2 - 1) / (d * y^2 - a)
		"""
		assert isinstance(y, FQ)
		assert y.m == JUBJUB_Q
		ysq = y * y
		xx = (ysq - 1) / (JUBJUB_D * ysq - JUBJUB_A)
		return cls(xx.sqrt(), y)

	@classmethod
	def from_x(cls, x):
		"""
		y^2 = ((a * x^2) / (d * x^2 - 1)) - (1 / (d * x^2 - 1))

		For every x coordinate, there are two possible points: (x, y) and (x, -y)
		"""
		assert isinstance(x, FQ)
		assert x.m == JUBJUB_Q
		xsq = x * x
		ax2 = JUBJUB_A * xsq
		dxsqm1 = (JUBJUB_D * xsq - 1).inv()
		ysq = dxsqm1 * (ax2 - 1)
		y = ysq.sqrt()
		return cls(x, y)

	@classmethod
	def from_hash(cls, entropy):
		"""
		HashToPoint (or Point.from_hash)

		Hashes the input entropy repeatedly, and interprets it as the Y
		coordinate then recovers the X coordinate, if no valid point can be
		recovered Y is incremented until a matching X coordinate is found.

		The point is guaranteed to be prime order and not the identity
		"""
		assert isinstance(entropy, bytes)
		entropy = sha256(entropy).digest()

		y = FQ(int.from_bytes(entropy, 'big'))
		while True:
			try:
				p = cls.from_y(y)
			except SquareRootError:
				y += 1
				continue

			# Multiply point by cofactor, ensures it's on the prime-order subgroup
			p = p * JUBJUB_C

			# Verify point is on prime-ordered sub-group
			if (p * JUBJUB_L) != Point.infinity():
				raise RuntimeError("Point not on prime-ordered subgroup")

			return p

	def as_proj(self):
		return ProjPoint(self.x, self.y, FQ(1))

	def as_etec(self):
		return EtecPoint(self.x, self.y, self.x*self.y, FQ(1))

	def as_point(self):
		return self

	def neg(self):
		"""
		Twisted Edwards Curves, BBJLP-2008, section 2 pg 2
		"""
		return Point(-self.x, self.y)

	def valid(self):
		"""
		Satisfies the relationship

			ax^2 + y^2 = 1 + d x^2 y^2
		"""
		xsq = self.x*self.x
		ysq = self.y*self.y
		return (JUBJUB_A * xsq) + ysq == (1 + JUBJUB_D * xsq * ysq)

	def add(self, other):
		assert isinstance(other, Point)
		if self.x == 0 and self.y == 0:
			return other
		(u1, v1) = (self.x, self.y)
		(u2, v2) = (other.x, other.y)
		u3 = (u1*v2 + v1*u2) / (FQ.one() + JUBJUB_D*u1*u2*v1*v2)
		v3 = (v1*v2 - JUBJUB_A*u1*u2) / (FQ.one() - JUBJUB_D*u1*u2*v1*v2)
		return Point(u3, v3)

	@staticmethod
	def infinity():
		return Point(FQ(0), FQ(1))


class ProjPoint(AbstractCurveOps, namedtuple('_ProjPoint', ('x', 'y', 'z'))):
	def rescale(self):
		return ProjPoint(self.x / self.z, self.y / self.z, FQ(1))

	def as_proj(self):
		return self

	def as_etec(self):
		"""
		(X, Y, Z) -> (X, Y, X*Y, Z)
		"""
		return EtecPoint(self.x, self.y, self.x*self.y, self.z)

	def as_point(self):
		assert self.z != 0
		inv_z = self.z.inv()
		return Point(self.x*inv_z, self.y*inv_z)

	def valid(self):
		return self.as_point().valid()

	@staticmethod
	def infinity():
		return ProjPoint(FQ(0), FQ(1), FQ(1))

	def neg(self):
		"""
		-(X : Y : Z) = (-X : Y : Z)
		"""
		return ProjPoint(-self.x, self.y, self.z)

	def add(self, other):
		"""
		add-2008-bbjlp
		https:/eprint.iacr.org/2008/013 Section 6
		Strongly unified
		"""
		assert isinstance(other, ProjPoint)
		if self == self.infinity():
			return other
		a = self.z * other.z
		b = a * a
		c = self.x * other.x
		d = self.y * other.y
		t0 = c * d
		e = JUBJUB_D * t0
		f = b - e
		g = b + e
		t1 = self.x + self.y
		t2 = other.x + other.y
		t3 = t1 * t2
		t4 = t3 - c
		t5 = t4 - d
		t6 = f * t5
		x3 = a * t6
		t7 = JUBJUB_A * c
		t8 = d - t7
		t9 = g * t8
		y3 = a * t9
		z3 = f * g
		return ProjPoint(x3, y3, z3)

	def double(self):
		"""
		dbl-2008-bbjlp https://eprint.iacr.org/2008/013

		From "Twisted Edwards Curves" - BBJLP

		# Doubling in Projective Twisted Coordinates
		> The following formulas compute (X3 : Y3 : Z3) = 2(X1 : Y1 : Z1)
		> in 3M + 4S + 1D + 7add, where the 1D is a multiplication by `a`.
		"""
		if self == self.infinity():
			return self.infinity()
		t0 = self.x + self.y
		b = t0 * t0
		c = self.x * self.x
		d = self.y * self.y
		e = JUBJUB_A * c
		f = e + d
		h = self.z * self.z
		t1 = 2 * h
		j = f - t1
		t2 = b - c
		t3 = t2 - d
		x3 = t3 * j
		t4 = e - d
		y3 = f * t4
		z3 = f * j
		return ProjPoint(x3, y3, z3)


class EtecPoint(AbstractCurveOps, namedtuple('_EtecPoint', ('x', 'y', 't', 'z'))):
	def as_etec(self):
		return self

	def as_point(self):
		"""
		Ignoring the T value, project from 3d X,Y,Z to 2d X,Y coordinates

			(X : Y : T : Z) -> (X/Z, Y/Z)
		"""
		inv_z = self.z.inv()
		return Point(self.x*inv_z, self.y*inv_z)

	def as_proj(self):
		"""
		The T value is dropped when converting from extended
		twisted edwards to projective edwards coordinates.

			(X : Y : T : Z) -> (X, Y, Z)
		"""
		return ProjPoint(self.x, self.y, self.z)

	@staticmethod
	def infinity():
		return EtecPoint(FQ(0), FQ(1), FQ(0), FQ(1))

	def neg(self):
		"""
		Twisted Edwards Curves Revisited - HWCD, pg 5, section 3

			-(X : Y : T : Z) = (-X : Y : -T : Z)
		"""
		return EtecPoint(-self.x, self.y, -self.t, self.z)

	def valid(self):
		return self.as_point().valid()

	def double(self):
		"""
		dbl-2008-hwcd
		"""
		if self == self.infinity():
			return self.infinity()
		a = self.x * self.x
		b = self.y * self.y
		t0 = self.z * self.z
		c = t0 * 2
		d = JUBJUB_A * a
		t1 = self.x + self.y
		t2 = t1 * t1
		t3 = t2 - a
		e = t3 - b
		g = d + b
		f = g - c
		h = d - b
		return EtecPoint(e*f, g*h, e*h, f*g)

	def add(self, other):
		"""
		3.1 Unified addition in ε^e
		"""
		assert isinstance(other, EtecPoint)
		if self == self.infinity():
			return other

		assert self.z != 0
		assert other.z != 0

		x1x2 = self.x * other.x
		y1y2 = self.y * other.y
		dt1t2 = (JUBJUB_D * self.t) * other.t
		z1z2 = self.z * other.z
		e = ((self.x + self.y) * (other.x + other.y)) - x1x2 - y1y2
		f = z1z2 - dt1t2
		g = z1z2 + dt1t2
		h = y1y2 - (JUBJUB_A * x1x2)

		return EtecPoint(e*f, g*h, e*h, f*g)

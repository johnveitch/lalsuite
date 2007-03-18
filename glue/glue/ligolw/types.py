# $Id$
#
# Copyright (C) 2006  Kipp C. Cannon
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2 of the License, or (at your
# option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General
# Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.


#
# =============================================================================
#
#                                   Preamble
#
# =============================================================================
#


"""
Definitions of type strings found in LIGO Light Weight XML files.

Notes.  To guarantee that a double-precision floating-point number can be
reconstructed exactly from its representation as a decimal number, one must
use 17 decimal digits;  for single-precision, the number is 9.  Python uses
only double-precision numbers, but LIGO Light Weight XML allows for
single-precision values, so I provide distinct format specifiers for those
cases here.  In both cases, I have elected to use 1 fewer digits than are
required to uniquely reconstruct the number:  the XML written by this
library is lossy.  I made this choice to reduce the file size, for example

>>> "%.17g" % 0.1
'0.10000000000000001'

while

>>> "%.16g" % 0.1
'0.1'

In this worst case, storing full precision increases the size of the XML by
more than an order of magnitude.  If you wish to make a different choice
for your files, for example if you wish your XML files to be lossless,
simply include the lines

	glue.ligolw.types.ToFormat.update({
		"real_4": u"%.9g",
		"real_8": u"%.17g",
		"float": u"%.9g",
		"double": u"%.17g"
	})

anywhere in your code, but before you write the document to a file.

References:

	- http://docs.sun.com/source/806-3568/ncg_goldberg.html
"""


__author__ = "Kipp Cannon <kipp@gravity.phys.uwm.edu>"
__date__ = "$Date$"[7:-2]
__version__ = "$Revision$"[11:-2]


#
# =============================================================================
#
#                               Type Information
#
# =============================================================================
#


IDTypes = [u"ilwd:char", u"ilwd:char_u"]
StringTypes = IDTypes + [u"char_s", u"char_v", u"lstring", u"string"]
IntTypes = [u"int_2s", u"int_2u", u"int_4s", u"int_4u", u"int_8s", u"int_8u", u"int"]
FloatTypes = [u"real_4", u"real_8", u"float", u"double"]
TimeTypes = [u"GPS", u"Unix", u"ISO-8601"]


Types = StringTypes + IntTypes + FloatTypes + TimeTypes


ToFormat = {
	u"char_s": u"\"%s\"",
	u"char_v": u"\"%s\"",
	u"ilwd:char": u"\"%s\"",
	u"ilwd:char_u": u"\"%s\"",
	u"lstring": u"\"%s\"",
	u"string": u"\"%s\"",
	u"int_2s": u"%d",
	u"int_2u": u"%u",
	u"int_4s": u"%d",
	u"int_4u": u"%u",
	u"int_8s": u"%d",
	u"int_8u": u"%u",
	u"int": u"%d",
	u"real_4": u"%.8g",
	u"real_8": u"%.16g",
	u"float": u"%.8g",
	u"double": u"%.16g"
}


ToPyType = {
	u"char_s": unicode,
	u"char_v": unicode,
	u"ilwd:char": str,
	u"ilwd:char_u": str,
	u"lstring": unicode,
	u"string": unicode,
	u"int_2s": int,
	u"int_2u": int,
	u"int_4s": int,
	u"int_4u": int,
	u"int_8s": int,
	u"int_8u": int,
	u"int": int,
	u"real_4": float,
	u"real_8": float,
	u"float": float,
	u"double": float
}


FromPyType = {
	str: u"lstring",
	unicode: u"lstring",
	int: u"int_4s",
	long: u"int_8s",
	float: u"real_8"
}


ToNumPyType = {
	u"int_2s": "int16",
	u"int_2u": "uint16",
	u"int_4s": "int32",
	u"int_4u": "uint32",
	u"int_8s": "int64",
	u"int_8u": "uint64",
	u"int": "int32",
	u"real_4": "float32",
	u"real_8": "float64",
	u"float": "float64",
	u"double": "float64"
}


FromNumPyType = {
	"int16": u"int_2s",
	"uint16": u"int_2u",
	"int32": u"int_4s",
	"uint32": u"int_4u",
	"int64": u"int_8s",
	"uint64": u"int_8u",
	"float32": u"real_4",
	"float64": u"real_8"
}


ToSQLiteType = {
	u"char_s": "TEXT",
	u"char_v": "TEXT",
	u"ilwd:char": "TEXT",
	u"ilwd:char_u": "TEXT",
	u"lstring": "TEXT",
	u"string": "TEXT",
	u"int_2s": "INTEGER",
	u"int_2u": "INTEGER",
	u"int_4s": "INTEGER",
	u"int_4u": "INTEGER",
	u"int_8s": "INTEGER",
	u"int_8u": "INTEGER",
	u"int": "INTEGER",
	u"real_4": "REAL",
	u"real_8": "REAL",
	u"float": "REAL",
	u"double": "REAL"
}


FromSQLiteType = {
	"TEXT": u"lstring",
	"STRING": u"lstring",
	"INTEGER": u"int_4s",
	"REAL": u"real_8"
}

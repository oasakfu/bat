#
# Copyright 2009-2011 Alex Fraser <alex@phatcore.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

import bge
import mathutils

RED   = mathutils.Vector([1.0, 0.0, 0.0, 1.0])
GREEN = mathutils.Vector([0.0, 1.0, 0.0, 1.0])
BLUE  = mathutils.Vector([0.0, 0.0, 1.0, 1.0])
YELLOW = RED + GREEN
YELLOW.w = 1.0
ORANGE = RED + (GREEN * 0.5)
ORANGE.w = 1.0
CYAN  = GREEN + BLUE
CYAN.w = 1.0
MAGENTA = RED + BLUE
MAGENTA.w = 1.0
WHITE = mathutils.Vector([1.0, 1.0, 1.0, 1.0])
BLACK = mathutils.Vector([0.0, 0.0, 0.0, 1.0])

_NAMED_COLOURS = {
    'red'   : '#ff0000',
    'green' : '#00ff00',
    'blue'  : '#0000ff',
    'black' : '#000000',
    'white' : '#ffffff',
    'darkred'   : '#331111',
    'darkgreen' : '#113311',
    'darkblue' : '#080833',

    'cargo' : '#36365a',
}

def srgb2lin(colour):
    '''Convert an sRGB colour to linear.'''
    def _srgb2lin_comp(component):
        if component < 0.0031308:
            return component * 12.92;
        else:
            return 1.055 * pow(component, 1.0/2.4) - 0.055;

    colour = colour.copy()
    for i in range(3):
        colour[i] = _srgb2lin_comp(colour[i])
    return colour

def lin2srgb(colour):
    '''Convert a linear colour to sRGB.'''
    def _lin2srgb_comp(component):
        if component < 0.04045:
            return component * (1.0 / 12.92)
        else:
            return pow((component + 0.055) * (1.0 / 1.055), 2.4)

    colour = colour.copy()
    for i in range(3):
        colour[i] = _lin2srgb_comp(colour[i])
    return colour

def draw_polyline(points, colour, cyclic=False):
    '''Like bge.render.drawLine, but operates on any number of points.'''

    for (a, b) in zip(points, points[1:]):
        bge.render.drawLine(a, b, colour[0:3])
    if cyclic and len(points) > 2:
        bge.render.drawLine(points[0], points[-1], colour[0:3])

def parse_colour(colstr):
    '''Parse a colour from a hexadecimal number; either "#rrggbb" or
    "#rrggbbaa". If no alpha is specified, a value of 1.0 will be used.

    Returns:
    A 4D vector compatible with object colour.
    '''

    if colstr[0] != '#':
        colstr = _NAMED_COLOURS[colstr.lower()]

    if colstr[0] != '#':
        raise ValueError('Hex colours need to start with a #')
    colstr = colstr[1:]

    if len(colstr) in {3, 4}:
        # half
        components = [(x + x) for x in colstr]
    elif len(colstr) in {6, 8}:
        # full
        components = [(x + y) for x,y in zip(colstr[0::2], colstr[1::2])]
    else:
        raise ValueError('Hex colours need to be #rgb, #rrggbb or #rrggbbaa.')

    colour = BLACK.copy()
    colour.x = int(components[0], 16)
    colour.y = int(components[1], 16)
    colour.z = int(components[2], 16)
    if len(components) == 4:
        colour.w = int(components[3], 16)
    else:
        colour.w = 255.0

    colour /= 255.0
    return colour

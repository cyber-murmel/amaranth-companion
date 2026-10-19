"""Drag and drop payloads.

Both ends of a drag need to agree on these, and the two ends sit in different
layers -- the canvas is a graphics view under ``module``, the palette is a
dock under ``windows``. Putting the names here keeps the view from importing
the window, which would be backwards.
"""

#: a block being dragged out of the palette onto the canvas; the payload is a
#: block id, as it appears in the library
BLOCK = "application/x-amaranth-companion-block"

#: a node being dragged off the canvas; the payload is its uuid
NODE = "application/x-amaranth-companion-node"

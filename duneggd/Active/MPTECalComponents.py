#!/usr/bin/env python
'''
Builds compontents for the MPT ECAL
'''

import gegede.builder
from gegede import Quantity as Q

from math import floor, atan, sin, cos, sqrt, pi


class MPTECalTileBuilder(gegede.builder.Builder):
    """Builds a single tile for the MPT Ecal

    The tile is built in the x,y plane with multiple layers.

    Attributes:
    dx,dy: x and y half-dimensions of the tile
    dz: a list specifying the depth of each layer
    lspacing: a list specifying the spacing after each layer
    mat: a list specifying the material of each layer
    filler_mat: the material between and outside of layers (fills in cracks)
    output_name: the name to give this tile 
                 (maybe used as a basename by the caller)
    """
    # set a .defaults which gegede will use to make data members
    # when configure is called

    defaults = dict(dx=Q("15mm"), dy=Q("15mm"),
                    dz=[Q('2mm'), Q('5mm'), Q('1mm')],
                    lspacing=[Q('0.1mm'), Q('0.1mm'), Q('2mm')],
                    mat=['Copper', 'Scintillator', 'FR4'],
                    filler_mat='Air',
                    output_name='MPTECalTile')

#    def configure(self, **kwds):
#        pass

    def depth(self):
        dzm = Q("0mm")
        for dz, lspace in zip(self.dz, self.lspacing):
            dzm += dz+lspace
        return dzm

    def construct(self, geom):
        # first make a mother volume to hold everything else
        dzm = self.depth()
        dzm = dzm/2.0  # Box() requires half dimensions
        print "dzm=", dzm
        # shapes need to have a unique name
        name=self.output_name
        tile_shape = geom.shapes.Box(name, self.dx, self.dy, dzm)
        tile_lv = geom.structure.Volume(name+"_vol",
                                        material=self.filler_mat,
                                        shape=tile_shape)
        # now loop to create layers

        skip = Q("0mm")  # no skipped space before the first layer
        cntr = 1
        zloc = Q("0mm")
        for dz, lspace, mat in zip(self.dz, self.lspacing, self.mat):
            lname = (self.output_name+"_L%i" % cntr)
            layer_shape = geom.shapes.Box(lname, self.dx, self.dy, dz/2.0)
            zloc = zloc+skip+dz/2.0
            print dz, lspace, mat, zloc
            layer_lv = geom.structure.Volume(lname+"_vol", material=mat,
                                             shape=layer_shape)
            # dzm is the half depth of the mother volume
            # we need to subtract it off to position layers
            # relative to the center of the mother
            layer_pos = geom.structure.Position(lname+"_pos",
                                                x='0mm', y='0mm', z=zloc-dzm)
            layer_pla = geom.structure.Placement(lname+"_pla",
                                                 volume=layer_lv,
                                                 pos=layer_pos)
            tile_lv.placements.append(layer_pla.name)

            skip = dz/2.0+lspace# set the skipped space before the next layer
            cntr += 1

        self.add_volume(tile_lv)
        return


class MPTECalStripBuilder(gegede.builder.Builder):
    """Builds a strip of ECalTiles

    The strip is built in the x,y plane with its length along x

    Attributes:
    length: the length of the strip,
           will compute the closest number of tiles to fit within this length
    ntiles: the number of tiles
    material: the default material of the strip (will fill in any cracks)
    extra_space=: space between tiles
    name: the name of this strip (maybe used as a basename by the caller)
    The caller can also set the tile locations manually 
    by assigning a list of (itile, xlocation) tuples to 
    the attribute input_tile_locations.
    """
    # set a .defaults which gegede will use to make data members
    # when configure is called

    defaults = dict(length=Q("1m"),
                    ntiles=0,
                    material='Air',
                    extra_space=Q("0.1mm"),
                    output_name='MPTECalStrip'
                    )
    
    def configure(self, **kwds):
        super(MPTECalStripBuilder, self).configure(**kwds)
        self.input_tile_locations = None
        
    def build_tile(self, geom, mother, lv, xloc, i):
        pos = geom.structure.Position(lv.name+"_%i_pos" % i,
                                      x=xloc, y='0mm', z='0mm')
        pla = geom.structure.Placement(lv.name+"_%i_pla" % i,
                                       volume=lv, pos=pos)

        mother.placements.append(pla.name)
        return

    def construct(self, geom):
        tile_builder = self.get_builder("MPTECalTileBuilder")
        tile_width = tile_builder.dx*2 + self.extra_space
        # has the number of tiles been specified?
        ntiles = 0
        if(self.ntiles > 0):
            ntiles = self.ntiles
        else:
            # need to figure out how many tiles
            ntiles = int(floor(self.length/tile_width))  # round explicitly
        strip_length = ntiles*tile_width

        # make the mother volume
        name = self.output_name
        print "In strip builder: strip_length=", strip_length
        strip_shape = geom.shapes.Box(name,
                                      dx=strip_length/2.0,
                                      dy=tile_builder.dy,
                                      dz=tile_builder.depth()/2.0)
        strip_lv = geom.structure.Volume(name+"_vol", shape=strip_shape,
                                         material=self.material)

        tile_lv = tile_builder.get_volume()
        for i, xloc in symmetric_arrangement(ntiles, tile_width):
            self.build_tile(geom, strip_lv, tile_lv, xloc, i)

        self.add_volume(strip_lv)
        return


def symmetric_arrangement(ntiles, tile_width):
    """Arrange ntiles of tile_width symmetrically around zero.

    Returns a tuple (int: itile,real: location)
    where itile ranges from -ntiles/2 to +ntiles/2 for even ntiles
    and -(ntiles-1)/2 to +(ntiles-1)/2 for odd ntiles
    """
    # I have notes explaining this
    def feven(w, i):
        return w*(i-0.5)

    def fodd(w, i): return w*i
    xloc = feven
    istart = 1
    iend = ntiles/2
    if ntiles % 2 != 0:
        xloc = fodd
        istart = 0
        iend = (ntiles-1)/2
    rval = []
    for i in range(istart, iend+1):
        rval.append((i, xloc(tile_width, i)))
        if(i != 0):
            rval.append((-i, -xloc(tile_width, i)))
    return rval


class MPTECalLayerBuilder(gegede.builder.Builder):
    """Builds a layer of ECalStrips

    Attributes:
    geometry=
      cylinder: build on a cylinder of radius r with angular coverage over
                phi_range=[start,end]. cylinder axis along z. phi is the
                usual angle in the x,y plane.
      xyplane: build out a rectangular plane of width x, height y
      cplane: build out a circular plane of radius r
    r, phi_range= used by the cylinder and cplane (just r) geometries
    x, y= used by the xyplane geometry
    material= material filling the mother volume (fills in any cracks)
    extra_space = space between strips
    output_name = name of this layer (maybe used as a basename by the caller)
    """
    # set a .defaults which gegede will use to make data members
    # when configure is called

    defaults = dict(geometry='cylinder',
                    r=Q("2.5m"), phi_range=[Q("0deg"), Q("360deg")],
                    material='Air',
                    extra_space=Q("0.1mm"),
                    output_name='MPTECalLayer'
                    )

#    def configure(self, **kwds):
#        super(MPTECalLayerBuilder, self).configure(**kwds)
#        self.all_tile_locations=None
#        if self.geometry=='cplane':
#            self.all_tile_locations=self.find_cplane_tile_locations(geom)

    def construct(self, geom):
        if self.geometry == 'cylinder':
            self.construct_cylinder(geom)
        elif self.geometry == 'cplane':
            self.construct_cplane(geom)
        return

    def construct_cylinder(self, geom):
        '''Constructs a cylinder, or partial cylinder, of ECalStrips'''
        strip_builder = self.get_builder("MPTECalStripBuilder")
        strip_lv = strip_builder.get_volume()
        ggd_shape = geom.store.shapes.get(strip_lv.shape)
        y_strip = (ggd_shape.dy+self.extra_space)*2
        z_strip = ggd_shape.dz*2
        strip_length = ggd_shape.dx*2

        # start by building the mother volume
        wanted_phi_coverage = self.phi_range[1]-self.phi_range[0]
        # dphi=angle covered by one strip with inside face at radius r
        dphi = 2*atan(y_strip/(2*self.r))
        n_strips = int(floor(wanted_phi_coverage/dphi))
        actual_phi_coverage = n_strips*dphi
        phi_coverage_diff = wanted_phi_coverage-actual_phi_coverage
        # adjust phi start and end points
        # checked that phi_end-phi_start=phi actual
        phi_start = self.phi_range[0]+phi_coverage_diff/2.0
        phi_end = self.phi_range[1]-phi_coverage_diff/2.0
        rmin = self.r
        print z_strip, rmin, y_strip, strip_length
        # figure out outer radius of the mother volume
        # some geometry here (in my notes)
        rmax2 = ((z_strip+rmin)**2 + (y_strip/2.0)**2)/Q("1mm**2")
        print rmax2
        rmax = sqrt(rmax2)*Q("1mm")
        lname=self.output_name
        # create the mother volume going from phi_start to phi_end
        layer_shape = geom.shapes.Tubs(lname, rmin=rmin, rmax=rmax,
                                       sphi=phi_start,
                                       dphi=actual_phi_coverage,
                                       dz=strip_length/2.0)

        layer_lv = geom.structure.Volume(lname+"_vol", shape=layer_shape,
                                         material=self.material)

        # now fill the mother volume with strips
        # the approach will be similar to what we did to make strips
        # out of tiles
        # we use symmetric_arrangement() to get strip locations
        # centered on phi=0 and then modify the location
        # to get the correct phi_start and phi_end
        temp_phi_start = -actual_phi_coverage/2
        phi_start_diff = temp_phi_start-phi_start
        for i, phi_loc in symmetric_arrangement(n_strips, dphi):
            phi_loc = phi_loc - phi_start_diff  # here is the modification
            xloc = (self.r+z_strip/2.0)*cos(phi_loc)
            yloc = (self.r+z_strip/2.0)*sin(phi_loc)
            zloc = Q("0mm")
#            print phi_loc
            pos = geom.structure.Position(strip_lv.name+"_%i_pos" % i,
                                          x=xloc, y=yloc, z=zloc)
            # Mike Kordosky July 20, 2018
            # ==============================================================
            # Regarding the rotation below: it's a mess.
            # 
            # The rotation x,y,z we provide here is used by the code
            # that reads the GDML to conduct rotations,
            # first about X, then about the (new) Y,
            # then about the (newer) Z. This is an "intrinsic" rotation, as
            # opposed to an "extrinsic" one in which the axes don't change.
            # I verified this in some simple cases by rotating the TileStrip
            # and looking to see what it did in the geometry viewer.
            # This convention would be useful if we were sitting in an
            # airplane and rotating it. It's pretty counterintuitive in
            # the case that we are external to objects and placing and
            # rotating them in space. <sigh>
            # 
            # The code that ultimately does the rotation
            # is CLHEP::HepRotation. I was able to look at it and reconstruct
            # the combined rotation matrix R_t after the three rotations.
            # This matrix has three angles: theta_x, theta_y, theta_z and
            # it's written out in my notes.
            #
            # A scheme of rotations about all three of
            # X, Y and Z in some order is called a Tait-Bryan rotation:
            #      https://en.wikipedia.org/wiki/Euler_angles
            # This differs from Euler rotations in that the latter features
            # the same axis twice (e.g., ZXZ)
            #
            # By comparing my matrix R_t with the matrix on the wiki page
            # (specifically Tait-Bryan X_1 Y_2 Z_3)
            # I see they disagree by a transpose and by the
            # sign of the angles, at least theta_y. The transpose could
            # be the difference between an active and passive transformation.
            # The wiki page says the matricies correspond to active
            # transformations and passive ones can be found as the
            # transpose. Also, I know my matrix corresponds to an intrinsic
            # rotation. Together these differences may explain the transpose
            # and sign issues.
            #
            # My method for finding the right rotation is desribed below.
            # 
            # The original orientation of the strip can be described by
            # two vectors:
            #
            # The first vector is a=(0,0,1), the vector normal
            # to the strip, pointing away from the third layer. We eventually
            # want this to point in the radial direction in cylindrical
            # coordinates, so the first layer of the strips (copper absorber)
            # faces inward. That direction is alpha=(cos(phi),sin(phi),0)
            #
            # The second vector b=(1,0,0) is taken to point along the strip
            # as it was originally constructed. After rotation we want
            # beta=(0,0,1).

            #
            # We want
            #    alpha = R_t a
            # and
            #    beta  = R_t b
            #
            # The game is to explicitly evaluate the RHS and then
            # see how to make it match the LHS by picking theta_x,y,z.
            # After some trial and error I found that solutions that
            # actually worked came from using the transpose of my R_t,
            # and -sy -> sy.  I don't really understand this.

            rot = geom.structure.Rotation(strip_lv.name+"_%i_rot" % i,
                                          x='90deg', y=(phi_loc-pi/2.0),
                                          z='90deg')
            pla = geom.structure.Placement(strip_lv.name+"_%i_pla" % i,
                                           volume=strip_lv, pos=pos, rot=rot)

            layer_lv.placements.append(pla.name)
        self.add_volume(layer_lv)
        return

    def construct_cplane(self, geom):
        '''Construct a plane of EcalTiles by tiling them inside a circle
        of radius self.r

        Extra space between tiles is controlled in the x direction
        by the TileStrip's extra space, and in the y direction by 
        this builder's extra space
        '''
        # find all_tile_locations in configure stage
        # Algorithim is to first find the length of a square that can fit
        # inside a radius rm<self.R. We will tile that and then try to add
        # to it along the outside to fill up the circle.
        tile_builder = self.get_builder("MPTECalTileBuilder")
        strip_builder = self.get_builder("MPTECalStripBuilder")
        tile_lv = tile_builder.get_volume()
        ggd_shape = geom.store.shapes.get(tile_lv.shape)
        
        # check that tiles are square
        tile_width = ggd_shape.dx*2 +strip_builder.extra_space
        tile_depth = ggd_shape.dz*2
        tile_widthy = ggd_shape.dy*2 + self.extra_space
        if tile_width != tile_widthy:
            raise RuntimeError(
                '''
                The ECalTile must be a square for construct_\\
                cplane()\n The requested tile has dimensions: dx=%f, dy=%f
                ''' % (ggd_shape.dx, ggd_shape.dy))
        # done with square chack

        # compute number of tiles on each edge of the inscribed square
        n_edge_tiles = int(floor(sqrt(2)*self.r/tile_width))
        # length of one side of the square
        lsquare = n_edge_tiles*tile_width  
        # radius of the circle that the square is inscribed in
        rm = lsquare/sqrt(2)
        
        # now get tile locations within the square
        # this is a list of tuples (itile, location)
        # because of the symmetry, the location is both the
        # x and y location
        tile_locations = symmetric_arrangement(n_edge_tiles, tile_width)
        # think of the return value as the x location of a row of
        # tiles at the top of the square, located at y=yrow
        # use symmetry to figure out what yrow is
        iys, ys = zip(*tile_locations)
        yrow = max(ys)
        starting_iymax = max(iys)
        # loop over each x tile location and see how many tiles
        # we can add in the +y direction while remaining inside
        # the circle of radius self.r
        new_tile_locations = []
        for ix, xloc in tile_locations:
            nadd, newys = self.tiles_to_add(xloc, yrow, tile_width, self.r)
            for yadd in newys:
                new_tile_locations.append((xloc, yadd))
        all_tile_locations = []
        for x in ys:
            for y in ys:
                all_tile_locations.append((x, y))
        ninscribed = len(all_tile_locations)
        print "number of tiles in inscribed square = %i" % (ninscribed)
        for x, y in new_tile_locations:
            for xx, yy in [(x, y), (x, -y), (y, x), (-y, x)]:
#                print 'xx, yy = %s , %s' % (xx, yy)
                all_tile_locations.append((xx, yy))
        nouter = len(all_tile_locations) - ninscribed
        print 'number of tiles outside inscribed square = %i' % (nouter)

        all_organized=organize_by_rows(all_tile_locations)
        # now build the mother volume
        lname = self.name
        layer_shape = geom.shapes.Tubs(lname, rmin='0mm', rmax=rm,
                                       sphi=Q("0deg"), dphi=Q("360deg"),
                                       dz=tile_depth/2.0)

        layer_lv = geom.structure.Volume(lname+"_vol", shape=layer_shape,
                                         material=self.material)
        
        # now fill the mother volume with tiles
        tname = tile_builder.name
        tile_lv = tile_builder.get_volume()
        for i, yrow in enumerate(all_organized):
            print 'yposition and nx --> %s and %i '%(yrow[0][1],len(yrow)) 
            for j, (x,y) in enumerate(yrow):
#                print 'placing tile %i_%i at (x,y) = (%s,%s)' % (i, j, x, y)
                pos = geom.structure.Position(tname+"_%i_%i_pos" % (i, j),
                                              x=x, y=y, z='0mm')
                pla = geom.structure.Placement(tname+"_%i_%i_pla" % (i, j),
                                               volume=tile_lv, pos=pos)
                layer_lv.placements.append(pla.name)
                

            
#        for i, (x, y) in enumerate(all_sorted):
#                pos = geom.structure.Position(tname+"_%i_pos" % i,
#                                              x=x, y=y, z='0mm')
#                pla = geom.structure.Placement(tname+"_%i_pla" % i,
#                                               volume=tile_lv, pos=pos)
#                layer_lv.placements.append(pla.name)

        self.add_volume(layer_lv)

    def tiles_to_add(self, x, y, w, r):
        '''Starting with a square tile of width w located at x,y 
        figure out how many tiles we can add while staying 
        within a radius r'''
        nadd = 0
        newys = []
        while self.is_tile_inside(x, y+nadd*w, w, self.r):
            newys.append(y+nadd*w)
            nadd = nadd+1
        return nadd, newys

    def is_tile_inside(self, x, y, w, r):
        '''Is the square tile with width w and centered on x,y 
        contained inside a circle of radius r?'''
        # it is sufficient to check that the 4 corners are inside the circle
        corners = [(x + w, y + w), (x + w, y - w),
                   (x - w, y + w), (x - w, y - w)]
        for xx, yy in corners:
            rc2 = (xx**2 + yy**2)/Q('1mm**2')
            rc = sqrt(rc2)*Q('1mm')
            if rc > r:
                return False
        return True


#        return all_tile_locations, rm, tile_depth

def organize_by_rows(all_tile_locations):
    ''' take in a list of (x,y) position tuples with all the tile locations
    and organize them into a list of lists of (x,y) tuples where each list 
    corresponds to one y row
    '''
    # first sort based on the y position
    all_sorted = sorted(all_tile_locations,
                        key=lambda entry: entry[1]/Q("1.0mm"))
    # now make a new structure, all_organized as a list of list of tuples
    # each list of tuples will correspond to one y row
    
    all_organized = []

    # append the first entry to our holding array
    temp_array = [all_sorted[0]]
    for x, y in all_sorted[1:]: # loop starting at the second entry
        if y == temp_array[0][1]:
            print 'x == temp_array[0][1] --> %s == %s'%(x, temp_array[0][1])
            print '    appending (%s, %s)' % (x, y)
            temp_array.append((x, y))
        else:
            print 'appending temp_array'
            all_organized.append(temp_array)
            temp_array = []
            print '   then appending (%s, %s)' % (x, y)
            temp_array.append((x, y))
    # loop ends without appending the last temp_array so do it here
    all_organized.append(temp_array)
    return all_organized

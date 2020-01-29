from __future__ import print_function
import unittest
import numpy as np
import discretize
from SimPEG import (utils, maps, regularization, data_misfit,
                    optimization, inverse_problem, directives,
                    inversion)
from SimPEG.potential_fields import gravity, get_dist_wgt

import shutil

np.random.seed(43)


class GravInvLinProblemTest(unittest.TestCase):

    def setUp(self):

        ndv = -100
        # Create a self.mesh
        dx = 5.

        hxind = [(dx, 5, -1.3), (dx, 5), (dx, 5, 1.3)]
        hyind = [(dx, 5, -1.3), (dx, 5), (dx, 5, 1.3)]
        hzind = [(dx, 5, -1.3), (dx, 6)]

        self.mesh = discretize.TensorMesh([hxind, hyind, hzind], 'CCC')

        # Get index of the center
        midx = int(self.mesh.nCx/2)
        midy = int(self.mesh.nCy/2)

        # Lets create a simple Gaussian topo and set the active cells
        [xx, yy] = np.meshgrid(self.mesh.vectorNx, self.mesh.vectorNy)
        zz = -np.exp((xx**2 + yy**2) / 75**2) + self.mesh.vectorNz[-1]

        # Go from topo to actv cells
        topo = np.c_[utils.mkvc(xx), utils.mkvc(yy), utils.mkvc(zz)]
        actv = utils.surface2ind_topo(self.mesh, topo, 'N')
        actv = np.where(actv)[0]

        # Create active map to go from reduce space to full
        self.actvMap = maps.InjectActiveCells(self.mesh, actv, -100)
        nC = len(actv)

        # Create and array of observation points
        xr = np.linspace(-20., 20., 20)
        yr = np.linspace(-20., 20., 20)
        X, Y = np.meshgrid(xr, yr)

        # Move the observation points 5m above the topo
        Z = -np.exp((X**2 + Y**2) / 75**2) + self.mesh.vectorNz[-1] + 5.

        # Create a MAGsurvey
        locXYZ = np.c_[utils.mkvc(X.T), utils.mkvc(Y.T), utils.mkvc(Z.T)]
        rxLoc = gravity.point_receiver(locXYZ)
        srcField = gravity.SourceField([rxLoc])
        survey = gravity.GravitySurvey(srcField)

        # We can now create a density model and generate data
        # Here a simple block in half-space
        model = np.zeros((self.mesh.nCx, self.mesh.nCy, self.mesh.nCz))
        model[(midx-2):(midx+2), (midy-2):(midy+2), -6:-2] = 0.5
        model = utils.mkvc(model)
        self.model = model[actv]

        # Create active map to go from reduce set to full
        actvMap = maps.InjectActiveCells(self.mesh, actv, ndv)

        # Create reduced identity map
        idenMap = maps.IdentityMap(nP=nC)

        # Create the forward model operator
        sim = gravity.IntegralSimulation(
                self.mesh,
                survey=survey,
                rhoMap=idenMap,
                actInd=actv,
                store_sensitivities='disk'
        )

        """
        # Compute linear forward operator and compute some data
        d = sim.fields(self.model)

        # Add noise and uncertainties (1nT)
        data = d + np.random.randn(len(d))*0.001
        wd = np.ones(len(data))*.001

        survey.dobs = data
        survey.std = wd
        """
        data = sim.make_synthetic_data(self.model, noise_floor=0.001, add_noise=True)

        # PF.Gravity.plot_obs_2D(survey.srcField.rxList[0].locs, d=data)

        # Create sensitivity weights from our linear forward operator
        wr = get_dist_wgt(self.mesh, locXYZ, actv, 2., 2.)
        wr = wr**2.

        # Create a regularization
        reg = regularization.Sparse(self.mesh, indActive=actv, mapping=idenMap)
        reg.cell_weights = wr
        reg.norms = np.c_[0, 0, 0, 0]
        reg.gradientType = 'component'
        # reg.eps_p, reg.eps_q = 5e-2, 1e-2

        # Data misfit function
        dmis = data_misfit.L2DataMisfit(simulation=sim, data=data)

        # Add directives to the inversion
        opt = optimization.ProjectedGNCG(maxIter=100, lower=-1., upper=1.,
                                         maxIterLS=20, maxIterCG=10,
                                         tolCG=1e-3)
        invProb = inverse_problem.BaseInvProblem(dmis, reg, opt, beta=1e+8)

        # Here is where the norms are applied
        IRLS = directives.Update_IRLS(f_min_change=1e-4,
                                      minGNiter=1)
        update_Jacobi = directives.UpdatePreconditioner()

        self.inv = inversion.BaseInversion(invProb,
                                           directiveList=[IRLS,
                                                          update_Jacobi])
        self.sim = sim


    def test_grav_inverse(self):

        # Run the inversion
        mrec = self.inv.run(self.model)
        residual = np.linalg.norm(mrec-self.model) / np.linalg.norm(self.model)
        print(residual)

        # plt.figure()
        # ax = plt.subplot(1, 2, 1)
        # midx = int(self.mesh.nCx/2)
        # self.mesh.plotSlice(self.actvMap*mrec, ax=ax, normal='Y', ind=midx,
        #                grid=True, clim=(0, 0.5))

        # ax = plt.subplot(1, 2, 2)
        # midx = int(self.mesh.nCx/2)
        # self.mesh.plotSlice(self.actvMap*self.model, ax=ax, normal='Y', ind=midx,
        #                grid=True, clim=(0, 0.5))
        # plt.show()

        self.assertTrue(residual < 0.05)


    def tearDown(self):
        # Clean up the working directory
        shutil.rmtree(self.sim.sensitivity_path)

if __name__ == '__main__':
    unittest.main()

#!/usr/bin/env python

""" AnDA_analog_forecasting.py: Apply the analog method on catalog of historical data to generate forecasts. """

__author__ = "Pierre Tandeo and Phi Huynh Viet"
__version__ = "1.1"
__date__ = "2019-02-06"
__maintainer__ = "Pierre Tandeo"
__email__ = "pierre.tandeo@imt-atlantique.fr"

import numpy as np
from sklearn.neighbors import KDTree
from AnDA_codes.AnDA_stat_functions import mk_stochastic, sample_discrete
from scipy.linalg import inv

def AnDA_analog_forecasting(x, AF):
    """ Apply the analog method on catalog of historical data to generate forecasts. """
    
    # initializations
    N, n = x.shape
    xf = np.zeros([N,n])
    xf_mean = np.zeros([N,n])
    stop_condition = 0
    i_var = np.array([0])
    
    # local or global analog forecasting
    while (stop_condition !=1):

        # in case of global approach
        if np.array_equal(AF.neighborhood, np.ones([n,n])):
            i_var_neighboor = np.arange(0,n)
            i_var = np.arange(0,n)
            stop_condition = 1

        # in case of local approach
        else:
            i_var_neighboor = np.where(AF.neighborhood[int(i_var),:]==1)[0]
            
        # find the indices and distances of the k-nearest neighbors (knn)
        kdt = KDTree(AF.catalog.analogs[:,i_var_neighboor], leaf_size=50, metric='euclidean')
        dist_knn, index_knn = kdt.query(x[:,i_var_neighboor], AF.k)
        
        # parameter of normalization for the kernels
        lambdaa = np.median(dist_knn)

        # compute weights
        if AF.k == 1:
            weights = np.ones([N,1])
        else:
            weights = mk_stochastic(np.exp(-np.power(dist_knn,2)/lambdaa))
        
        # for each member/particle
        for i_N in range(0,N):
            
            # initialization
            xf_tmp = np.zeros([AF.k,np.max(i_var)+1])
            
            # method "locally-constant"
            if (AF.regression == 'locally_constant'):
                
                # compute the analog forecasts
                xf_tmp[:,i_var] = AF.catalog.successors[np.ix_(index_knn[i_N,:],i_var)]
                
                # weighted mean and covariance
                xf_mean[i_N,i_var] = np.sum(xf_tmp[:,i_var]*np.repeat(weights[i_N,:][np.newaxis].T,len(i_var),1),0)
                E_xf = (xf_tmp[:,i_var]-np.repeat(xf_mean[i_N,i_var][np.newaxis],AF.k,0)).T
                cov_xf = 1.0/(1.0-np.sum(np.power(weights[i_N,:],2)))*np.dot(np.repeat(weights[i_N,:][np.newaxis],len(i_var),0)*E_xf,E_xf.T)

            # method "locally-incremental"
            elif (AF.regression == 'increment'):
                
                # compute the analog forecasts
                xf_tmp[:,i_var] = np.repeat(x[i_N,i_var][np.newaxis],AF.k,0) + AF.catalog.successors[np.ix_(index_knn[i_N,:],i_var)]-AF.catalog.analogs[np.ix_(index_knn[i_N,:],i_var)]
                
                # weighted mean and covariance
                xf_mean[i_N,i_var] = np.sum(xf_tmp[:,i_var]*np.repeat(weights[i_N,:][np.newaxis].T,len(i_var),1),0)
                E_xf = (xf_tmp[:,i_var]-np.repeat(xf_mean[i_N,i_var][np.newaxis],AF.k,0)).T
                cov_xf = 1.0/(1-np.sum(np.power(weights[i_N,:],2)))*np.dot(np.repeat(weights[i_N,:][np.newaxis],len(i_var),0)*E_xf,E_xf.T)

            # method "locally-linear"
            elif (AF.regression == 'local_linear'):
         
                # define analogs, successors and weights
                X = AF.catalog.analogs[np.ix_(index_knn[i_N,:],i_var_neighboor)]                
                Y = AF.catalog.successors[np.ix_(index_knn[i_N,:],i_var)]                
                w = weights[i_N,:][np.newaxis]
                
                # compute centered weighted mean and weighted covariance
                Xm = np.array([np.sum(X*np.repeat(w.T,len(i_var_neighboor),1),0)])
                Xc = X - np.repeat(Xm,np.shape(X)[0],0)
                
                # use SVD decomposition to compute principal components
                U,S,V = np.linalg.svd(Xc,full_matrices=False)
                ind = np.where(S/np.sum(S)>0.01)[0] # keep eigen values higher than 1%
                
                # regression on principal components
                Xr = np.hstack((np.ones([np.shape(X)[0],1]),np.dot(Xc,V.T[:,ind])))
                Cxx = np.dot(np.repeat(np.array([np.matrix.flatten(w)]).T,np.shape(Xr)[1],1).T*Xr.T,Xr)
                Cxx2 = np.dot(np.repeat(np.array([np.matrix.flatten(w**2)]).T,np.shape(Xr)[1],1).T*Xr.T,Xr)
                Cxy = np.dot(np.repeat(np.array([np.matrix.flatten(w)]).T,np.shape(Y)[1],1).T*Y.T,Xr)
                inv_Cxx = inv(Cxx) # in case of error here, increase the number of analogs (AF.k option)
                beta = np.dot(inv_Cxx,Cxy.T)
                X0 = x[i_N,i_var_neighboor]-Xm
                X0r = np.hstack((np.ones([np.shape(X0)[0],1]),np.dot(X0,V.T[:,ind])))
                 
                # weighted mean
                xf_mean[i_N,i_var] = np.dot(X0r,beta)
                pred = np.dot(Xr,beta)
                res = Y-pred
                xf_tmp[:,i_var] = np.tile(xf_mean[i_N,i_var],(AF.k,1))+res
                
                # weigthed covariance
                cov_xfc = np.dot(np.repeat(np.array([np.matrix.flatten(w)]).T,np.shape(res)[1],1).T*res.T,res)/(1-np.trace(np.dot(Cxx2,inv_Cxx)))
                cov_xf = cov_xfc*(1+np.trace(Cxx2@inv_Cxx@X0r.T@X0r@inv_Cxx))
                
                # constant weights for local linear
                weights[i_N,:] = 1.0/len(weights[i_N,:])
                
            # error
            else:
                print("Error: choose AF.regression between 'locally_constant', 'increment', 'local_linear' ")
                quit()
            
            '''
            # method "globally-linear" (to finish)
            elif (AF.regression == 'global_linear'):
                ### REMARK: USE i_var_neighboor IN THE FUTURE! ####
                xf_mean[i_N,:] = AF.global_linear.predict(np.array([x[i_N,:]]))
                if n==1:
                    cov_xf = np.cov((AF.catalog.successors - AF.global_linear.predict(AF.catalog.analogs)).T)[np.newaxis][np.newaxis]
                else:
                    cov_xf = np.cov((AF.catalog.successors - AF.global_linear.predict(AF.catalog.analogs)).T)
            
            # method "locally-forest" (to finish)
            elif (AF.regression == 'local_forest'):
                ### REMARK: USE i_var_neighboor IN THE FUTURE! #### 
                xf_mean[i_N,:] = AF.local_forest.predict(np.array([x[i_N,:]]))
                if n==1:
                    cov_xf = np.cov(((AF.catalog.successors - np.array([AF.local_forest.predict(AF.catalog.analogs)]).T).T))[np.newaxis][np.newaxis]
                else:
                    cov_xf = np.cov((AF.catalog.successors - AF.local_forest.predict(AF.catalog.analogs)).T)
                # weighted mean and covariance
                #xf_tmp[:,i_var] = AF.local_forest.predict(AF.catalog.analogs[np.ix_(index_knn[i_N,:],i_var)]);
                #xf_mean[i_N,i_var] = np.sum(xf_tmp[:,i_var]*np.repeat(weights[i_N,:][np.newaxis].T,len(i_var),1),0)
                #E_xf = (xf_tmp[:,i_var]-np.repeat(xf_mean[i_N,i_var][np.newaxis],AF.k,0)).T;
                #cov_xf = 1.0/(1.0-np.sum(np.power(weights[i_N,:],2)))*np.dot(np.repeat(weights[i_N,:][np.newaxis],len(i_var),0)*E_xf,E_xf.T);
            '''
            
            # Gaussian sampling
            if (AF.sampling =='gaussian'):
                # random sampling from the multivariate Gaussian distribution
                xf[i_N,i_var] = np.random.multivariate_normal(xf_mean[i_N,i_var],cov_xf)
            
            # Multinomial sampling
            elif (AF.sampling =='multinomial'):
                # random sampling from the multinomial distribution of the weights
                i_good = sample_discrete(weights[i_N,:],1,1)
                xf[i_N,i_var] = xf_tmp[i_good,i_var]
            
            # error
            else:
                print("Error: choose AF.sampling between 'gaussian', 'multinomial' ")
                quit()

        # stop condition
        if (np.array_equal(i_var,np.array([n-1])) or (len(i_var) == n)):
            stop_condition = 1;
             
        else:
            i_var = i_var + 1
            
    return xf, xf_mean; # end

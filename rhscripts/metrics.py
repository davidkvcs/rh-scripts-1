#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri May 21 12:47:52 2021

@author: claes
"""

from skimage import measure
import collections
import numpy as np
from scipy.spatial import distance
import torchio as tio
from scipy.spatial import cKDTree

def dice_similarity(arr1: np.ndarray, arr2: np.ndarray) -> float:
    """
    Dice-score from two numpy arrays
    """
    return 1. - distance.dice( arr1.flatten(), arr2.flatten() )

def getLesionLevelDetectionMetrics( reference_image: np.ndarray, predicted_image: np.ndarray ) -> collections.namedtuple:
    """

    Lesion-level detection metrics

    Will count number reference regions part of prediction rather than
    predicted lesions that are part of reference (V2 behavior)

    Parameters
    ----------
    reference_image : np.ndarray
        Reference image of zeros (background) and ROIs (above zero).
    predicted_image : np.ndarray
        New image of zeros (background) and ROIs (above zero).

    Returns
    -------
    metrics
        Named tuple of metrics. Get e.g. TP by calling metrics.TP.

    """

    predicted_clusters = measure.label( predicted_image, background=0 )
    true_clusters = measure.label( reference_image, background=0 )
    overlap = np.multiply(true_clusters, predicted_image)

    numTrueClusters = np.max(true_clusters)
    numPredClusters = np.max(predicted_clusters)

    TP = len(np.unique(overlap)) - 1 # 1 for BG
    FN = numTrueClusters-TP
    FP = numPredClusters - (len(np.unique((overlap>0).astype(int) * predicted_clusters))-1)

    recall = 0 if numTrueClusters == 0 else TP / numTrueClusters
    precision = 0 if numPredClusters == 0  else TP  / (TP+FP)
    f1 = any([precision,recall]) and 2*(precision*recall)/(precision+recall) or 0

    Metrics = collections.namedtuple("Metrics", ["precision", "recall", "f1", "TP", "FP", "FN"])
    return Metrics(precision=precision, recall=recall, f1=f1, TP=TP, FP=FP, FN=FN)

def getLesionLevelDetectionMetricsV2( reference_image: np.ndarray, predicted_image: np.ndarray ) -> collections.namedtuple:
    """

    Lesion-level detection metrics

    Will count TP as predicted lesions that are part of reference rather than
    reference lesions part of prediction (V1 behavior).

    Parameters
    ----------
    reference_image : np.ndarray
        Reference image of zeros (background) and ROIs (above zero).
    predicted_image : np.ndarray
        New image of zeros (background) and ROIs (above zero).

    Returns
    -------
    metrics
        Named tuple of metrics. Get e.g. TP by calling metrics.TP.

    """

    predicted_clusters = measure.label( predicted_image, background=0 )
    true_clusters = measure.label( reference_image, background=0 )

    predicted_overlap = np.multiply(predicted_clusters, reference_image)
    TP = len(np.unique(predicted_overlap))-1 # BG
    FP = np.max(predicted_clusters)-TP

    reference_overlap = np.multiply(true_clusters, predicted_image)
    FN = np.max(true_clusters) - (len(np.unique(reference_overlap))-1)

    P = FN+TP
    numPredClusters = TP+FP

    recall = 0 if P == 0 else TP / P
    precision = 0 if numPredClusters == 0  else TP  / numPredClusters
    f1 = any([precision,recall]) and 2*(precision*recall)/(precision+recall) or 0

    Metrics = collections.namedtuple("Metrics", ["precision", "recall", "f1", "TP", "FP", "FN"])
    return Metrics(precision=precision, recall=recall, f1=f1, TP=TP, FP=FP, FN=FN)

def hausdorff_distance( arr1: np.ndarray, arr2: np.ndarray, axial_orientation: int=0 ) -> float:
    """
    Calculate the maximum hausdorff distance between two 2D images

    If 3D array, return the maximum across the slices.
    """
    if len(np.squeeze(arr1).shape) == 3:
        max_distance = 0
        for z in range(arr1.shape[axial_orientation]):
            u = np.take(arr1,axis=axial_orientation,indices=z)
            v = np.take(arr2,axis=axial_orientation,indices=z)
            max_distance = max( max_distance, hausdorff_distance(u,v) )
        return max_distance
    return max(distance.directed_hausdorff(arr1, arr2)[0], distance.directed_hausdorff(arr2, arr1)[0])

def hausdorff_distance_with_resampling(lab1_nii, lab2_nii):
    '''
    Code copied from 
    https://github.com/voreille/hecktor/blob/master/src/evaluation/scores.py

    DGK 13-dep-2022: I added a resampling step of resampling to 1x1x1mm.
    This ensures that the return value is a physical distance in mm.

    Input should be binary nifti files. 

    TODO: in case lab1 and lab2 include a different number of slices after resampling to 1x1x1mm, need to resample lab1 like lab2 first.
    '''

    transform = tio.Resample(1)
    lab1 = tio.LabelMap(lab1_nii)
    lab2 = tio.ScalarImage(lab2_nii)
    lab1_transformed = transform(lab1)
    lab2_transformed = transform(lab2)
    lab1_t_np = np.squeeze(lab1_transformed.numpy())
    lab2_t_np = np.squeeze(lab2_transformed.numpy())
    
    if lab1_t_np.shape == lab2_t_np.shape:
        a_points = np.transpose(np.nonzero(lab1_t_np))
        b_points = np.transpose(np.nonzero(lab2_t_np))

        # Handle empty sets properly:
        # - if both sets are empty, return zero
        # - if only one set is empty, return infinity
        if len(a_points) == 0:
            return 0 if len(b_points) == 0 else np.inf
        elif len(b_points) == 0:
            return np.inf

        return max(max(cKDTree(a_points).query(b_points, k=1)[0]),
                   max(cKDTree(b_points).query(a_points, k=1)[0]))
    else:
        return 'Check manually. Shapes not equal.'
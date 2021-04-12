#!/usr/bin/env python

import os, glob
try:
    import pydicom as dicom
    from pydicom.filereader import InvalidDicomError #For rtx2mnc
except ImportError:
    import dicom
    from dicom.filereader import InvalidDicomError #For rtx2mnc
import pyminc.volumes.factory as pyminc
import numpy as np
import datetime
import cv2
from rhscripts.utils import listdir_nohidden, bbox_ND

def findExtension(sourcedir,extensions = [".ima", ".IMA", ".dcm", ".DCM"]):
    """Return the number of files with one of the extensions, 
    or -1 no files were found, or if more than one type of extension is found

    Parameters
    ----------
    sourcedir : string
        Path to the directory to look for files with extensions
    extensions : string list, optional
        Extensions to look for, each mutually exclusive

    Notes
    -----
    If none of the folders in sourcedir contains the extensions, it will fail.

    Examples
    --------
    >>> from rhscripts.conversion import findExtension
    >>> if findExtension('folderA') != -1:
    >>>     print("Found files in folderA")
    Found files in folderA
    """
    counts = [0]*len(extensions)
    c = 0
    for ext in extensions:
        files = glob.glob(os.path.join(sourcedir,'*' + ext) )
        counts[c] = len(files)
        c += 1
    if sum(counts) > max(counts) or sum(counts) == 0:
        return -1
    else:
        return extensions[counts.index(max(counts))]

def look_for_dcm_files(folder):
    """Return first folder found with one of the extensions, 
    or -1 no files were found, or if more than one type of extension is found

    Parameters
    ----------
    folder : string
        Path to the directory to crawl for files with extensions

    Notes
    -----
    Only the path to the first occurence of files will be returned

    Examples
    --------
    >>> from rhscripts.conversion import look_for_dcm_files
    >>> dicomfolder = look_for_dcm_files('folderA')
    """
    if findExtension(folder) != -1:
        return folder
    for root,subdirs,files in os.walk(folder):
        if len(subdirs) > 0:
            continue
        if not len(files) > 0:
            continue
        if findExtension(root) != -1:
            return root
    return -1
        
def dcm_to_mnc(folder,target='.',fname=None,dname=None,verbose=False,checkForFileEndings=True):
    """Convert a folder with dicom files to minc

    Parameters
    ----------
    folder : string
        Path to the directory to crawl for files
    target : string, optional
        Path to the install prefix
    fname : string, optional
        Name of the minc file, if not set, use minc-toolkit default
    dname : string, optional
        Name of the folder to place the minc file into, if not set, use minc-toolkit default
    verbose : boolean, optional
        Set the verbosity
    checkForFileEndings : boolean, optional
        If set, crawl for a folder with dicom file endings, otherwise just use input

    Notes
    -----
    

    Examples
    --------
    >>> from rhscripts.conversion import dcm_to_mnc
    >>> dcm_to_mnc('folderA',target='folderB',fname='PETCT',dname='mnc',checkForFileEndings=False)
    """
    dcmcontainer = look_for_dcm_files(folder) if checkForFileEndings else folder
    
    if dcmcontainer == -1:
        print("Could not find dicom files in container..")
        exit(-1)

    cmd = 'dcm2mnc -usecoordinates -clobber '+dcmcontainer+'/* '+target
    if not fname is None:
        cmd += ' -fname "'+fname+'"'
    if not dname is None:
        cmd += ' -dname '+dname

    if verbose:
        print("Command %s" % cmd)

    os.system(cmd)


def mnc_to_dcm(mncfile,dicomcontainer,dicomfolder,verbose=False,modify=False,description=None,study_id=None,checkForFileEndings=True,forceRescaleSlope=False):  
    """Convert a minc file to dicom

    Parameters
    ----------
    mncfile : string
        Path to the minc file
    dicomcontainer : string
        Path to the directory containing the dicom container
    dicomfolder : string
        Path to the output dicom folder
    verbose : boolean, optional
        Set the verbosity
    modify : boolean, optional
        Create new SeriesInstanceUID and SOPInstanceUID
        Default on if description or id is set
    description : string, optional
        Sets the SeriesDescription tag in the dicom files
    id : int, optional
        Sets the SeriesNumber tag in the dicom files
    forceRescaleSlope : boolean, optional
        Forces recalculation of rescale slope

    Examples
    --------
    >>> from rhscripts.conversion import mnc_to_dcm
    >>> mnc_to_dcm('PETCT_new.mnc','PETCT','PETCT_new',description="PETCT_new",id="600")
    """

    ## TODO
    # Add slope and intercept (e.g. for PET)
    # Fix max in numpy conversion
    # 4D MRI
    # time series data
    
    if verbose:
        print("Converting to DICOM")

    if description or study_id:
        modify = True
    
    if checkForFileEndings:
        dcmcontainer = look_for_dcm_files(dicomcontainer)
        if dcmcontainer == -1:
            print("Could not find dicom files in container..")
            exit(-1)
    else:
        dcmcontainer = dicomcontainer

    # Get information about the dataset from a single file
    firstfile = listdir_nohidden(dcmcontainer)[0]
    try:
        ds=dicom.read_file(os.path.join(dcmcontainer,firstfile).decode('utf8'))
    except AttributeError:
        ds=dicom.read_file(os.path.join(dcmcontainer,firstfile))
    # Load the minc file
    minc = pyminc.volumeFromFile(mncfile)
    np_minc = np.array(minc.data)
    #np_minc = np.array(minc.data,dtype=ds.pixel_array.dtype)
    minc.closeVolume()
    # Check that the correct number of files exists
    if verbose:
        print("Checking files ( %d ) equals number of slices ( %d )" % (len(listdir_nohidden(dcmcontainer)), np_minc.shape[0]))
    assert len(listdir_nohidden(dcmcontainer)) == np_minc.shape[0]

    ## Prepare for MODIFY HEADER
    try:
        newSIUID = unicode(datetime.datetime.now()) # Python2
    except:
        newSIUID = str(datetime.datetime.now()) #Python3
    newSIUID = newSIUID.replace("-","")
    newSIUID = newSIUID.replace(" ","")
    newSIUID = newSIUID.replace(":","")
    newSIUID = newSIUID.replace(".","")
    newSIUID = '1.3.12.2.1107.5.2.38.51014.' + str(newSIUID) + '11111.0.0.0' 

    np_minc = np.maximum( np_minc, 0 )

    # Create output folder
    if not os.path.exists(dicomfolder):
        os.mkdir(dicomfolder)

    # Calculate new rescale slope if not 1
    RescaleSlope = 1.0
    doUpdateRescaleSlope = False
    if hasattr(ds, 'RescaleSlope'):
        if forceRescaleSlope:
            RescaleSlope = np.max(np_minc) / float(ds.LargestImagePixelValue) + 0.000000000001
            doUpdateRescaleSlope = True
            if verbose:
                print(f"Setting RescaleSlope from {ds.RescaleSlope} to {RescaleSlope}")
        elif not ds.RescaleSlope == RescaleSlope:
            if np.max(np_minc)/ds.RescaleSlope+ds.RescaleIntercept > 32767:
                old_RescaleSlope = ds.RescaleSlope
                vol_max = np.max(np_minc)
                RescaleSlope = vol_max / float(ds.LargestImagePixelValue) + 0.000000000001
                doUpdateRescaleSlope = True
                if verbose:
                    print("MAX EXCEEDED - RECALCULATING RESCALE SLOPE")
                    print("WAS: %f\nIS: %f" % (old_RescaleSlope,RescaleSlope))
            else:
                RescaleSlope = ds.RescaleSlope

    # List files, do not need to be ordered
    for f in listdir_nohidden(dcmcontainer):
        try:
            ds=dicom.read_file(os.path.join(dcmcontainer,f).decode('utf8'))
        except AttributeError:
            ds=dicom.read_file(os.path.join(dcmcontainer,f))
        i = int(ds.InstanceNumber)-1

        # Check inplane-dimension is the same
        assert ds.pixel_array.shape == (np_minc.shape[1],np_minc.shape[2])

        # UPDATE CHANGE RESCALESLOPE
        if doUpdateRescaleSlope:
            ds.RescaleSlope = RescaleSlope

        data_slice = np_minc[i,:,:].astype('double')
        data_slice /= float(RescaleSlope)
        if np.max(data_slice) > 32767:
            print("OOOOPS - NEGATIVE VALUES OCCURED!!!")
            print(np.max(data_slice),ds.RescaleSlope,RescaleSlope)
        data_slice = data_slice.astype('int16') # To signed short

        # Insert pixel-data
        ds.PixelData = data_slice.tostring()

        if modify:
            if verbose:
                print("Modifying DICOM headers")

            # Set information if given
            if not description == None:
                ds.SeriesDescription = description
            if not study_id == None:
                ds.SeriesNumber = study_id

            # Update SOP - unique per file
            try:
                newSOP = unicode(datetime.datetime.now())  # Python2
            except:
                newSOP = str(datetime.datetime.now())  # Python3
            newSOP = newSOP.replace("-","")
            newSOP = newSOP.replace(" ","")
            newSOP = newSOP.replace(":","")
            newSOP = newSOP.replace(".","")
            newSOP = '1.3.12.2.1107.5.2.38.51014.' + str(newSOP) + str(i+1)
            ds.SOPInstanceUID = newSOP

            # Update MediaStorageSOPInstanceUID - unique per file
            try:
                newMSOP = unicode(datetime.datetime.now())  # Python2
            except:
                newMSOP = str(datetime.datetime.now())  # Python3
            newMSOP = newMSOP.replace("-","")
            newMSOP = newMSOP.replace(" ","")
            newMSOP = newMSOP.replace(":","")
            newMSOP = newMSOP.replace(".","")
            newMSOP = newMSOP[-10:]
            newMSOP = '1.3.12.2.1107.5.1.4.99999.15359' + str(newMSOP) + str(i+1)
            ds.file_meta.MediaStorageSOPInstanceUID = newMSOP

            # Same for all files
            ds.SeriesInstanceUID = newSIUID

        fname = "dicom_%04d.dcm" % int(ds.InstanceNumber)
        ds.save_as(os.path.join(dicomfolder,fname))

    if verbose:
        print("Output written to %s" % dicomfolder)

def mnc_to_dcm_4D(mncfile,dicomcontainer,dicomfolder,verbose=False,modify=False,description=None,study_id=None,checkForFileEndings=True,forceRescaleSlope=False):  
    """Convert a minc file to dicom

    Parameters
    ----------
    mncfile : string
        Path to the minc file
    dicomcontainer : string
        Path to the directory containing the dicom container
    dicomfolder : string
        Path to the output dicom folder
    verbose : boolean, optional
        Set the verbosity
    modify : boolean, optional
        Create new SeriesInstanceUID and SOPInstanceUID
        Default on if description or id is set
    description : string, optional
        Sets the SeriesDescription tag in the dicom files
    id : int, optional
        Sets the SeriesNumber tag in the dicom files
    forceRescaleSlope : boolean, optional
        Forces recalculation of rescale slope

    Examples
    --------
    >>> from rhscripts.conversion import mnc_to_dcm
    >>> mnc_to_dcm_4D('PETCT_new.mnc','PETCT','PETCT_new',description="PETCT_new",id="600")
    """

    ## TODO
    # Add slope and intercept (e.g. for PET)
    # Fix max in numpy conversion
    # 4D MRI
    # time series data
    
    if verbose:
        print("Converting to DICOM")

    if description or study_id:
        modify = True
    
    if checkForFileEndings:
        dcmcontainer = look_for_dcm_files(dicomcontainer)
        if dcmcontainer == -1:
            print("Could not find dicom files in container..")
            exit(-1)
    else:
        dcmcontainer = dicomcontainer

    # Get information about the dataset from a single file
    firstfile = listdir_nohidden(dcmcontainer)[0]
    try:
        ds=dicom.read_file(os.path.join(dcmcontainer,firstfile).decode('utf8'))
    except AttributeError:
        ds=dicom.read_file(os.path.join(dcmcontainer,firstfile))
    # Load the minc file
    minc = pyminc.volumeFromFile(mncfile)
    timeslots = ds.NumberOfTimeSlots
    numberofslices = ds.NumberOfSlices
    np_minc = np.array(minc.data)#,dtype=ds.pixel_array.dtype) # dtype is redefined later..
    minc.closeVolume()

    # Check that the correct number of files exists
    if verbose:
        print("Checking files ( %d ) equals number of slices ( %d )" % (len(listdir_nohidden(dcmcontainer)), np_minc.shape[0]))
    assert len(listdir_nohidden(dcmcontainer)) == np_minc.shape[0]*np_minc.shape[1]

    ## Prepare for MODIFY HEADER
    try:
        newSIUID = unicode(datetime.datetime.now()) # Python2
    except:
        newSIUID = str(datetime.datetime.now()) #Python3
    newSIUID = newSIUID.replace("-","")
    newSIUID = newSIUID.replace(" ","")
    newSIUID = newSIUID.replace(":","")
    newSIUID = newSIUID.replace(".","")
    newSIUID = '1.3.12.2.1107.5.2.38.51014.' + str(newSIUID) + '11111.0.0.0' 

    np_minc = np.maximum( np_minc, 0 )

    # Create output folder
    if not os.path.exists(dicomfolder):
        os.mkdir(dicomfolder)

    # Calculate new rescale slope if not 1
    RescaleSlope = 1.0
    doUpdateRescaleSlope = False
    if hasattr(ds, 'RescaleSlope'):
        if forceRescaleSlope:
            RescaleSlope = np.max(np_minc) / float(ds.LargestImagePixelValue) + 0.000000000001
            doUpdateRescaleSlope = True
            if verbose:
                print(f"Setting RescaleSlope from {ds.RescaleSlope} to {RescaleSlope}")
        elif not ds.RescaleSlope == RescaleSlope:
            if np.max(np_minc)/ds.RescaleSlope+ds.RescaleIntercept > 32767:
                old_RescaleSlope = ds.RescaleSlope
                vol_max = np.max(np_minc)
                RescaleSlope = vol_max / float(ds.LargestImagePixelValue) + 0.000000000001
                doUpdateRescaleSlope = True
                if verbose:
                    print("MAX EXCEEDED - RECALCULATING RESCALE SLOPE")
                    print("WAS: %f\nIS: %f" % (old_RescaleSlope,RescaleSlope))
            else:
                RescaleSlope = ds.RescaleSlope

    # List files, do not need to be ordered
    for f in listdir_nohidden(dcmcontainer):
        try:
            ds=dicom.read_file(os.path.join(dcmcontainer,f).decode('utf8'))
        except AttributeError:
            ds=dicom.read_file(os.path.join(dcmcontainer,f))
        i = int(ds.InstanceNumber)-1

        # Check inplane-dimension is the same
        assert ds.pixel_array.shape == (np_minc.shape[2],np_minc.shape[3])

        # Scale pixel-data by intercept and rescale-slope
        #print(f,float(ds.RescaleSlope))
        #data_slice = np.divide(np_minc[i,:,:] - float(ds.RescaleIntercept), ds.RescaleSlope)
        
        slice_time = i // numberofslices
        slice_number = i % numberofslices
        #print(f,i,slice_time,slice_number)

        data_slice = np_minc[slice_time,slice_number,:,:]

        # UPDATE CHANGE RESCALESLOPE
        if doUpdateRescaleSlope:
            ds.RescaleSlope = RescaleSlope
        data_slice = data_slice.astype('double')
        data_slice /= float(RescaleSlope)
        if np.max(data_slice) > 32767:
            print("OOOOPS - NEGATIVE VALUES OCCURED!!!")
            print(np.max(data_slice),ds.RescaleSlope,RescaleSlope)
        data_slice = data_slice.astype('int16') # To signed short

        # Insert pixel-data
        ds.PixelData = data_slice.tostring()
        #ds.LargestImagePixelValue = LargestImagePixelValue

        if modify:
            if verbose:
                print("Modifying DICOM headers")

            # Set information if given
            if not description == None:
                ds.SeriesDescription = description
            if not study_id == None:
                ds.SeriesNumber = study_id

            # Update SOP - unique per file
            try:
                newSOP = unicode(datetime.datetime.now())  # Python2
            except:
                newSOP = str(datetime.datetime.now())  # Python3
            newSOP = newSOP.replace("-","")
            newSOP = newSOP.replace(" ","")
            newSOP = newSOP.replace(":","")
            newSOP = newSOP.replace(".","")
            newSOP = '1.3.12.2.1107.5.2.38.51014.' + str(newSOP) + str(i+1)
            ds.SOPInstanceUID = newSOP

            # Update MediaStorageSOPInstanceUID - unique per file
            try:
                newMSOP = unicode(datetime.datetime.now())  # Python2
            except:
                newMSOP = str(datetime.datetime.now())  # Python3
            newMSOP = newMSOP.replace("-","")
            newMSOP = newMSOP.replace(" ","")
            newMSOP = newMSOP.replace(":","")
            newMSOP = newMSOP.replace(".","")
            newMSOP = newMSOP[-10:]
            newMSOP = '1.3.12.2.1107.5.1.4.99999.15359' + str(newMSOP) + str(i+1)
            ds.file_meta.MediaStorageSOPInstanceUID = newMSOP

            # Same for all files
            ds.SeriesInstanceUID = newSIUID

        fname = "dicom_%04d.dcm" % int(ds.InstanceNumber)
        ds.save_as(os.path.join(dicomfolder,fname))

    if verbose:
        print("Output written to %s" % dicomfolder)

def rtdose_to_mnc(dcmfile,mncfile):
    
    """Convert dcm file (RD dose distribution) to minc file

    Parameters
    ----------
    dcmfile : string
        Path to the dicom file (RD type)    
    mncfile : string
        Path to the minc file

    Examples
    --------
    >>> from rhscripts.conversion import rtdose_to_mnc
    >>> rtdose_to_mnc('RD.dcm',RD.mnc')
    """

    # Load the dicom
    ds = dicom.dcmread(dcmfile)
    
    # Extract the starts and steps of the x,y,z space
    starts = ds.ImagePositionPatient
    steps = [float(i) for i in ds.PixelSpacing];
    if not (ds.SliceThickness==''):
        dz = ds.SliceThickness
    elif 'GridFrameOffsetVector' in ds: 
        dz = ds.GridFrameOffsetVector[1] -ds.GridFrameOffsetVector[0]
    else:
        raise IOError("Cannot determine slicethickness!")
    steps.append(dz)
    
    #reorder the starts and steps!
    myorder = [2,1,0]
    starts = [ starts[i] for i in myorder]
    myorder = [2,0,1]
    steps = [ steps[i] for i in myorder]
    #change the sign (e.g. starts=[1,-1,-1].*starts)
    starts = [a*b for a,b in zip([1,-1,-1],starts)]
    steps = [a*b for a,b in zip([1,-1,-1],steps)]
    
    #Get the pixel data and scale it correctly
    dose_array = ds.pixel_array*float(ds.DoseGridScaling)
    
    # Write the output minc file
    out_vol = pyminc.volumeFromData(mncfile,dose_array,dimnames=("zspace", "yspace", "xspace"),starts=starts,steps=steps)
    out_vol.writeFile() 
    out_vol.closeVolume() 

def rtx_to_mnc(dcmfile,mnc_container_file,mnc_output_file,verbose=False,copy_name=False,dry_run=False,roi_name=None,crop_area=False):
    
    """Convert dcm file (RT struct) to minc file

    Parameters
    ----------
    dcmfile : string
        Path to the dicom file (RT struct)    
    mnc_container_file : string
        Path to the minc file that is the container of the RT struct
    mnc_output_file : string
        Path to the minc output file
    verbose : boolean, optional
        Default = False (if true, print info)
    copy_name : boolean, optional
        Default = False, If true the ROI name from Mirada is store in Minc header
    dry_run : boolean, optional
        Default = False, If true, only the roi names will be printed, no files are saved
    roi_name : string, optional
        Specify a name, only ROIs matching this description will be created
    crop_area : boolean, optional
        Instead of the full area matching the mnc_container, crop the area to match values > 0
    Examples
    --------
    >>> from rhscripts.conversion import rtx_to_mnc
    >>> rtx_to_mnc('RTstruct.dcm',PET.mnc','RTstruct.mnc',verbose=False,copy_name=True)
    """

    try:
        RTSS = dicom.read_file(dcmfile) 
            
        ROIs = RTSS.ROIContourSequence

        if verbose or dry_run:
            print(RTSS.StructureSetROISequence[0].ROIName)
            print("Found",len(ROIs),"ROIs")

        if not dry_run:
            volume = pyminc.volumeFromFile(mnc_container_file)


        for ROI_id,ROI in enumerate(ROIs):

            # Create one MNC output file per ROI
            RTMINC_outname = mnc_output_file if len(ROIs) == 1 else mnc_output_file[:-4] + "_" + str(ROI_id) + ".mnc"
            if not dry_run:
                RTMINC = pyminc.volumeLikeFile(mnc_container_file,RTMINC_outname)
            contour_sequences = ROI.ContourSequence

            if verbose or dry_run:
                print(" --> Found",len(contour_sequences),"contour sequences for ROI:",RTSS.StructureSetROISequence[ROI_id].ROIName)

            # Only save for ROI with specific name
            if not roi_name == None and not roi_name == RTSS.StructureSetROISequence[ROI_id].ROIName:
                if verbose:
                    print("Skipping ")
                continue

            if not dry_run:
                for contour in contour_sequences:
                    assert contour.ContourGeometricType == "CLOSED_PLANAR"

                    current_slice_i_print = 0
                    
                    if verbose:
                        print("\t",contour.ContourNumber,"contains",contour.NumberOfContourPoints)
                    
                    world_coordinate_points = np.array(contour.ContourData)
                    world_coordinate_points = world_coordinate_points.reshape((contour.NumberOfContourPoints,3))
                    current_slice = np.zeros((volume.getSizes()[1],volume.getSizes()[2]))
                    voxel_coordinates_inplane = np.zeros((len(world_coordinate_points),2))
                    current_slice_i = 0
                    for wi,world in enumerate(world_coordinate_points):
                        voxel = volume.convertWorldToVoxel([-world[0],-world[1],world[2]])
                        current_slice_i = voxel[0]
                        voxel_coordinates_inplane[wi,:] = [voxel[2],voxel[1]]
                    current_slice_inner = np.zeros((volume.getSizes()[1],volume.getSizes()[2]),dtype=np.float)
                    converted_voxel_coordinates_inplane = np.array(np.round(voxel_coordinates_inplane),np.int32)
                    cv2.fillPoly(current_slice_inner,pts=[converted_voxel_coordinates_inplane],color=1)

                    RTMINC.data[int(round(current_slice_i))] += current_slice_inner                    

            if not dry_run:
                # Remove even areas - implies a hole.
                RTMINC.data[RTMINC.data % 2 == 0] = 0

                # Save cropped area of label, or full volume
                if crop_area:
                    # TODO
                    print("Functionality not implemented yet")
                    exit(-1)
                else:
                    RTMINC.writeFile()
                    RTMINC.closeVolume()

                if copy_name:
                    print('minc_modify_header -sinsert dicom_0x0008:el_0x103e="'+RTSS.StructureSetROISequence[ROI_id].ROIName+'" '+RTMINC_outname)
                    os.system('minc_modify_header -sinsert dicom_0x0008:el_0x103e="'+RTSS.StructureSetROISequence[ROI_id].ROIName+'" '+RTMINC_outname)
        if not dry_run:
            volume.closeVolume()

    except InvalidDicomError:
        print("Could not read DICOM RTX file",args.RTX)
        exit(-1)

def hu2lac(infile,outfile,kvp=None,mrac=False,verbose=False):

    """Convert CT-HU to LAC @ 511 keV

    Parameters
    ----------
    infile : string
        Path to the input mnc file   
    outfile : string
        Path to the outputmnc file 
    kvp : int, optional
        Integer that specify the kVp on CT scan (overwrites the search for a value)       
    mrac: boolean, optional
        if set, scales the LAC [cm^-1] by 10000
    verbose : boolean, optional
        Set the verbosity       
    Examples
    --------
    >>> from rhscripts.conversion import hu2lac
    >>> hu2lac('CT_hu.mnc',CT_lac.mnc',kvp = 120)
    """
    if not kvp:
        kvp = os.popen('mincinfo -attvalue dicom_0x0018:el_0x0060 ' + infile + ' -error_string noKVP').read().rstrip()
        if kvp == 'noKVP':
            print('Cant find KVP in header. Are you sure this a CT image?')
            return
        else:
            kvp = int(kvp)
    print('kvp = ' + str(kvp))            

    if mrac:
        fscalefactor = 10000
    else:
        fscalefactor = 1
        
    if kvp==100:
        cmd = 'minccalc -expression \"if(A[0]<52){ ((A[0]+1000)*0.000096)*'+str(fscalefactor)+'; } else { ((A[0]+1000)*0.0000443+0.0544)*'+str(fscalefactor)+'; }\" ' + infile + ' ' + outfile + ' -clobber'
    elif kvp == 120:
        cmd = 'minccalc -expression \"if(A[0]<47){ ((A[0]+1000)*0.000096)*'+str(fscalefactor)+'; } else { ((A[0]+1000)*0.0000510+0.0471)*'+str(fscalefactor)+'; }\" ' + infile + ' ' + outfile + ' -clobber'
    else:
        print('No conversion for this KVP!')
        return        

    if verbose:
        print(cmd)

    os.system(cmd)


def lac2hu(infile,outfile,kvp=None,mrac=False,verbose=False):

    """Convert LAC @ 511 keV to  CT-HU

    Parameters
    ----------
    infile : string
        Path to the input mnc file   
    outfile : string
        ath to the outputmnc file 
    kvp : int, optional
        Integer that specify the kVp on CT scan (overwrites the search for a value)     
    mrac: boolean, optional
        if set, accounts for the fact that LAC [cm^-1] is multiplyed by 10000
    verbose : boolean, optional
        Set the verbosity        
    Examples
    --------
    >>> from rhscripts.conversion import lac2hu
    >>> lac2hu('CT_lac.mnc',CT_hu.mnc',kvp = 120)
    """
    if not kvp:
        kvp = os.popen('mincinfo -attvalue dicom_0x0018:el_0x0060 ' + infile + ' -error_string noKVP').read().rstrip()
        if kvp == 'noKVP':
            print('Cant find KVP in header. Are you sure this a CT image?')
            return
        else:
            kvp = int(kvp)
    print('kvp = ' + str(kvp))       
        
    if mrac:
        fscalefactor = 10000
    else:
        fscalefactor = 1
        
    if kvp==100:
        breakpoint = ((52+1000)*0.000096)*fscalefactor
        cmd = 'minccalc -expression \"if(A[0]<'+str(breakpoint)+'){((A[0]/'+str(fscalefactor)+')/0.000096)-1000; } else { ((A[0]/'+str(fscalefactor)+')-0.0544)/0.0000443 - 1000; }\" ' + infile + ' ' + outfile + ' -clobber'
    elif kvp == 120:
        breakpoint = ((47+1000)*0.000096)*fscalefactor        
        cmd = 'minccalc -expression \"if(A[0]<'+str(breakpoint)+'){((A[0]/'+str(fscalefactor)+')/0.000096)-1000; } else { ((A[0]/'+str(fscalefactor)+')-0.0471)/0.0000510 - 1000; }\" ' + infile + ' ' + outfile + ' -clobber'
    else:
        print('No conversion for this KVP!')
        return

    if verbose:
        print(cmd)
    
    os.system(cmd)                 

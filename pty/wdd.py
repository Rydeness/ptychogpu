import numpy as np
import numba
from scipy import ndimage as scnd
from ..util import image_utils as iu
from ..beam import gen_probe as gp
from ..pty import pty_utils as pu

@numba.jit
def psi_multiply(data_1,
                 data_2):
    """
    Multiply two 4D datasets
    
    Parameters
    ----------
    data_1: ndarray
            First array, will not be conjugated
    data_2: ndarray
            Second array, WILL be complex conjugated 
    
    Returns
    -------
    multiplied_data: ndarray
    
    Notes
    -----
    Small Numba accelerated wrapper for multiplying two 4D datasets,
    where the complex conjugate of the second array is multiplied by
    the first array
    
    :Authors:
    Debangshu Mukherjee <mukherjeed@ornl.gov>
    """
    data_size = (np.asarray(data_1.shape)).astype(int)
    multiplied_data = (np.zeros((data_size[0],data_size[1],data_size[2],data_size[3]))).astype('complex')
    for jj in range(data_size[3]):
        for ii in range(data_size[2]):
            multiplied_data[:,:,ii,jj] = np.multiply(data_1[:,:,ii,jj],np.conj(data_2[:,:,ii,jj]))
    return multiplied_data

@numba.jit(parallel=True)
def fft_wigner_probe(aperture_mrad,
                     voltage,
                     image_size,
                     calibration_pm,
                     intensity_param=1):
    """
    Generate a Wigner distribution function
    of an electron beam
    
    Parameters
    ----------
    aperture_mrad:   float
                     Probe forming aperture in milliradians
    voltage:         float
                     Electron accelerating voltage in kilovolts
    image_size:      tuple
                     Size of the beam matrix
    calibration_pm:  float
                     Real-space pixel size
    intensity_param: float
                     Normalization of the Wigner intensity to compare
                     with experimental data. 
                     Default is 1
    
    Returns
    -------
    wigner_beam: ndarray
                 4D ndarray of the Wigner distribution function
                 of the electron beam
    
    Notes
    -----
    The Wigner distribution function as defined by Nellist and Rodenburg
    is a 'shifted' Fourier function. At every position, the Fourier distribution
    function is shifted by the inverse Fourier distance. Thus, if the function
    is a top hat function, it is zero, at every value double the radius of the 
    top-hat aperture function. It is this function that gives rise to double
    resolution in WDD ptychography and also because the magnitude of the Wigner
    distribution is the thickest for the top-hat aperture, and thinnest at twice
    the top-hat aperture, the contrast transfer function when using WDD is 
    always peaked at the top hat aperture.
    
    References
    ----------
    Yang, Hao, et al. "Electron ptychographic phase imaging of light elements 
    in crystalline materials using Wigner distribution deconvolution." 
    Ultramicroscopy 180 (2017): 173-179.
    
    :Authors:
    Debangshu Mukherjee <mukherjeed@ornl.gov>
    """
    image_y = image_size[0]
    image_x = image_size[1]
    tb = gp.make_probe(aperture_mrad,voltage,image_x,image_y,calibration_pm)
    fourier_beam = tb/intensity_param
    wigner_beam = np.zeros((image_x,image_y,image_x,image_y)).astype(complex)
    for rows_x in range(image_x):
        for rows_y in range(image_y):
            xpos = rows_x - (image_x/2)
            ypos = rows_y - (image_y/2)
            moved_fourier_beam = scnd.interpolation.shift(fourier_beam,(-xpos,-ypos))
            convolved_beam = np.multiply(np.conj(fourier_beam),moved_fourier_beam)
            wigner_beam[:,:,rows_x,rows_y] = convolved_beam
    return wigner_beam

def wdd(data4D,
        aperture_mrad,
        voltage,
        image_size,
        calibration_pm):
    """
    Perform single side band ptychography
    
    Parameters
    ----------
    data4D:         ndarray
                    Four dimensional resized dataset
    aperture_mrad:  float
                    Probe forming aperture in milliradians
    voltage:        float
                    Electron accelerating voltage in kilovolts
    image_size:     tuple
                    Size of the beam matrix
    calibration_pm: float
                    Real-space pixel size
    
    Returns
    -------
    single_side_band: ndarray
                      Complex single side band object
                      function
    
    Notes
    -----
    First the 4D data is Fourier transformed in the two CBED dimensions 
    to get dataFT, and then this complex 4D dataset (dataFT) is inverse 
    Fourier transformed along the two scanning dimensions to get dataIFT. 
    This dataIFT is the data that will look like 'trotters', at diffraction
    spots. This is then multiplied with a Wigner distribution function of
    an ideal beam to generate the SSB reconstruction.
    
    References
    ----------
    Yang, Hao, et al. "Electron ptychographic phase imaging of light elements 
    in crystalline materials using Wigner distribution deconvolution." 
    Ultramicroscopy 180 (2017): 173-179.
    
    See Also
    --------
    sample_4D
    
    :Authors:
    Debangshu Mukherjee <mukherjeed@ornl.gov>
    """
    image_y = image_size[0]
    image_x = image_size[1]
    electron_beam = gp.make_probe(aperture_mrad,voltage,(image_x,image_y),calibration_pm)
    diffractogram_intensity = np.sum(np.mean(data4D,axis=(2,3)))
    mainbeam_intensity = (np.abs(electron_beam) ** 2).sum()
    intensity_changer = (mainbeam_intensity/diffractogram_intensity) ** 0.5
    wigner_beam = fft_wigner_probe(aperture_mrad,voltage,(image_x,image_y),calibration_pm,intensity_changer)
    dataFT = np.fft.fftshift((np.fft.fft2(data4D,axes=(2,3))),axes=(2,3))
    dataIFT = np.fft.ifftshift((np.fft.ifft2(dataFT,axes=(0,1))),axes=(0,1))
    inverse_wigner = np.fft.ifftshift((np.fft.ifft2(wigner_beam,axes=(0,1))),axes=(0,1))
    Psi_Wigner = pu.sparse4D(psi_multiply(dataIFT,np.conj(inverse_wigner)),(np.abs(inverse_wigner) ** 2))
    wig_shape = np.asarray(np.shape(Psi_Wigner))
    wigner_deconv = np.fft.fft2(np.multiply((Psi_Wigner[1 + int(wig_shape[0]/2),1 + int(wig_shape[1]/2),:,:]),test_beam))
    return wigner_deconv
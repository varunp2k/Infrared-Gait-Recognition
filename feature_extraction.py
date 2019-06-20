import cv2
import math
import numpy as np
import pywt
from scipy.spatial import distance as dist


def draw_rectangle(reading):

    """
    Draws a bounding rectangle using contours for the given image
    :param reading: image for which bounding rectangle is to be drawn
    :return: size_rect; coordinates and size of bounding rectangle (x, y, w, h)
             reading; final image with bounding rectangle
    """

    size_rect = []
    # Converting frame to gray scale
    frame = cv2.cvtColor(reading, cv2.COLOR_BGR2GRAY)

    # Setting a non - rectangular kernel for dilation
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    dilate = cv2.dilate(frame, kernel)

    # Finding contours for dilated image
    _, cont, hier = cv2.findContours(dilate.copy(), cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    for con, hi in zip(cont, hier[0]):
        if hi[3] != -1:
            cv2.drawContours(dilate, [con], 0, 255, 3)

    # Performing Erosion and morphological opening (erosion followed by dilation)
    image = cv2.erode(dilate, kernel)
    image = cv2.morphologyEx(image, cv2.MORPH_OPEN, kernel)

    # Finding contours of processed image
    _, cont, hierarchy = cv2.findContours(image.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Loop for all contours in the final image
    for c in cont:

        # Getting coordinates of bounding rectangle for each contour
        x, y, w, h = cv2.boundingRect(c)
        if len(cont) > 1:
            size_rect.append([w, h, x, y])
        else:
            size_rect = [w, h, x, y]
        cv2.rectangle(reading, (x, y), (x + w, y + h), (0, 255, 0), 2)

    return reading, size_rect


def calc_stride_dist(image):

    """
    Calculates the distance between the 2 feet for each input image
    :param image: Input image for distance calculation
    :return: distance; The distance between 2 feet
    """

    # Generating a mask for lower part of gait sequence
    mask = np.zeros(image.shape[:2], np.uint8)
    mask[190:240, 0:320] = 255
    image_and = cv2.bitwise_and(image, image, mask=mask)

    # Obtaining size of rectangles for input image
    result, rect_size = draw_rectangle(image_and)

    # If 2 rectangles are detected (feet are apart)
    if len(rect_size) == 2:
        cent1 = (rect_size[0][2] + rect_size[0][0]/2, rect_size[0][3] + rect_size[0][1]/2)
        cent2 = (rect_size[1][2] + rect_size[1][0]/2, rect_size[1][3] + rect_size[1][1]/2)
        distance = dist.euclidean(cent2, cent1)

    # Setting distance to 1 to avoid calculated distances when the feet are together
    else:
        distance = 1

    # Returning the computed distance
    return distance


def calc_gait_cycle(cap):

    """
    Estimates gait cycles depending on step length
    :param cap: Video Capture object for video sequence
    :return: step_count; number of steps in given gait sequence
             gait_sizes; nested list for size of rectangles in a gait step
             n_size; number of frames in each gait steps
             step_lengths; list of distances between the 2 feet for each step
    """

    step_count = 0      # Number of gait steps in video sample
    coefficients = []   # List for storing haar wavelet coefficients for each cycle
    coeff_temp = []     # List for storing haar wavelet coefficients for each frame
    gait_sizes = []     # Nested list that stores sizes of rectangles for gait cycles
    cycle_sizes = []    # Stores size of rectangles for each gait cycle
    step_lengths = []   # List that stores step length for each gait cycle of each frame
    frame_count = 0     # Number of frames in each gait cycle
    n_size = []         # List for storing number of frames in each gait cycle
    gap_legs = []       # List for storing gap between feet in each frame
    while True:

        # Reading each frame from the video
        ret, reading = cap.read()

        if ret is False:
            break

        frame_count += 1

        temp = cv2.cvtColor(reading, cv2.COLOR_BGR2GRAY)
        c_a, (c_h, c_v, c_d) = pywt.dwt2(temp, 'haar')
        coeff_temp.append((c_a, c_h, c_v, c_d))

        # Calculating step length and rectangle dimensions for image
        stride_dist = calc_stride_dist(reading)
        reading, size_rect = draw_rectangle(reading)
        cycle_sizes.append(size_rect)

        # Checking if the maximum step length is encountered (ending of one step)
        if (len(gap_legs) > 2 and stride_dist < gap_legs[len(gap_legs) - 1]) and stride_dist > 40:
            gait_sizes.append(cycle_sizes)
            n_size.append(frame_count)
            step_lengths.append(gap_legs)
            coefficients.append(coeff_temp)
            coeff_temp = []
            gap_legs = []
            step_count += 1
            cycle_sizes = []

        # Appending stride_length to list
        gap_legs.append(stride_dist)

    return step_count, gait_sizes, n_size, step_lengths, coefficients


def calc_spatial_component(step_count, rect_sizes, num_frames):

    """
    Calculates Spatial Components from extracted binary silhouettes
    :param step_count: Number of gait cycles
    :param rect_sizes: Sizes of bounding rectangle for each frame
    :param num_frames: List of number of frames in each gait cycle
    :return: mean_height; average height of rectangle
             mean_width; average width of rectangle
             mean_angle; average angle of diagonal of rectangle wrt horizontal
             mean_ar; average aspect ratio of rectangle
    """

    # Setting all mean values to 0
    mean_height = 0
    mean_width = 0
    mean_angle = 0
    mean_ar = 0

    # Iterating over each gait step and calculating means
    for i in range(step_count):
        h = sum([element[0] for element in rect_sizes[i]]) / num_frames[i]
        w = sum([element[1] for element in rect_sizes[i]]) / num_frames[i]
        a = sum([math.atan(element[1]/element[0]) for element in rect_sizes[i]]) / num_frames[i]
        ar = sum([element[1]/element[0] for element in rect_sizes[i]]) / num_frames[i]

        # Adding cycle wise averages to overall average
        mean_height += h
        mean_width += w
        mean_angle += a
        mean_ar += ar

    # Returning average values of spatial features
    return mean_height * 2/step_count, mean_width * 2/step_count, mean_angle * 2/step_count, mean_ar * 2/step_count


def calc_temporal_component(step_lengths):

    """
    Calculates the temporal components from given step lengths
    :param step_lengths: Distance between both feet in each frame of each step
    :return: step_len; mean step length from all steps
             stride_len; mean stride length from all frames
             mean_cadence; mean value of cadence in
             velocity; velocity of subject in length/sec
    """

    # Cadence = number of steps / minute
    # Velocity = stride length * 0.5 * cadence

    step_len = 0
    mean_cadence = 0

    for i in range(len(step_lengths)):

        step_len += max(step_lengths[i])            # Maximum size of step from list
        no_of_frames = len(step_lengths[i])         # Number of frames in each step
        no_of_steps = 1/no_of_frames                # Number of steps in each frame
        cad = no_of_steps * cv2.CAP_PROP_FPS        # Cadence = number of steps in each frame * FPS
        mean_cadence += cad                         # Mean value of cadence

    mean_cadence /= len(step_lengths)
    step_len /= len(step_lengths)
    stride_len = 2 * step_len
    speed = stride_len * 0.5 * mean_cadence

    return step_len, stride_len, mean_cadence, speed


def calc_stand_deviation(coefficient_list, frames, mean):

    """
    Calculates the standard deviation given the list of coefficients
    :param coefficient_list: List of values of each coefficient (1 from low freq, 2 from detailed freq)
    :param frames: number of frames in each step
    :param mean: mean of the given coefficients
    :return: standard deviation of the list of coefficients
    """

    constant = math.pow(1/(frames - 1), 0.5)
    list_sum = [math.pow(ele - mean, 2) for ele in coefficient_list]
    sum_squares = np.sum(list_sum, axis=None)
    sd = constant * math.pow(sum_squares, 0.5)
    return sd


def calc_wavelet_component(haar_coeff, noof_frames):

    """
    Calculates the wavelet coefficients calculated using a 2D single level DWT
    :param haar_coeff:
    :param noof_frames: List of number of frames in each step of gait sample
    :return: Wavelet_feature; List containing the mean and standard deviations of the coefficients

    Format: [[mean1, stand1], [mean2, stand2], [mean3, stand3]]
    """
    wavelet_feature = []
    for index in range(len(haar_coeff)):

        # Taking sum of coefficients to enable calculations
        # One low frequency coefficient and 2 detailed frequency coefficients
        coefficient_1 = [np.sum(element[0], axis=None) for element in haar_coeff[index]]
        coefficient_2 = [np.sum(element[1], axis=None) for element in haar_coeff[index]]
        coefficient_3 = [np.sum(element[2], axis=None) for element in haar_coeff[index]]

        # Calculating mean and standard deviation for 1st list of coefficients
        mean_1 = np.sum(coefficient_1, axis=None) / noof_frames[index]
        stand_1 = calc_stand_deviation(coefficient_1, noof_frames[index], mean_1)

        # Calculating mean and standard deviation for 2nd list of coefficients
        mean_2 = np.sum(coefficient_2, axis=None) / noof_frames[index]
        stand_2 = calc_stand_deviation(coefficient_2, noof_frames[index], mean_2)

        # Calculating mean and standard deviation for 3rd list of coefficients
        mean_3 = np.sum(coefficient_3, axis=None) / noof_frames[index]
        stand_3 = calc_stand_deviation(coefficient_3, noof_frames[index], mean_3)

        wavelet_feature.append([[mean_1, stand_1], [mean_2, stand_2], [mean_3, stand_3]])

    return wavelet_feature


# Creating Video Capture Object
video = cv2.VideoCapture('E:\Softwares\PyCharm\PyCharm Community Edition 2018.2.4'
                         '\Projects\Gait Analysis\Walking_001\Walk2.mp4')

step_cnt, sizes, step_frames, step_lens, haar_coefficients = calc_gait_cycle(video)

# step_cnt     : Number of steps in given gait sequence
# sizes        : Size of rectangles in each gait step
# step_frames  : Number of frames in each step
# step_lens    : Distance between feet in each frame

height, width, angle, aspect = calc_spatial_component(step_cnt, sizes, step_frames)

# height    : mean height of bounding rectangle
# width     : mean width of bounding rectangle
# angle     : mean angle of bounding rectangle
# aspect    : mean aspect ratio of bounding rectangle

step_length, stride_length, cadence, velocity = (calc_temporal_component(step_lens))

# step_length   : length of each step
# stride_length : length of each stride (2 * step length)
# cadence       : cadence of subject (number of steps per second)
# velocity      : velocity of subject ( cadence * 0.5 * stride length)

wavelet_component = calc_wavelet_component(haar_coefficients, step_frames)

# wavelet_component : List of tuples containing mean and standard deviation

video.release()
cv2.destroyAllWindows()

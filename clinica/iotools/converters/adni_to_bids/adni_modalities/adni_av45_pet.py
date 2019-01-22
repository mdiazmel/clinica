# coding: utf-8

"""
 Module for converting PET_AV45 of ADNI
"""

__author__ = "Jorge Samper-Gonzalez"
__copyright__ = "Copyright 2016-2019 The Aramis Lab Team"
__credits__ = ["Sabrina Fontanella"]
__license__ = "See LICENSE.txt file"
__version__ = "0.1.0"
__maintainer__ = "Jorge Samper-Gonzalez"
__email__ = "jorge.samper-gonzalez@inria.fr"
__status__ = "Development"


def convert_adni_av45_pet(source_dir, csv_dir, dest_dir, subjs_list=None):
    """
    Convert PET AV45 of ADNI

    Args:
        source_dir: path to the ADNI directory
        csv_dir: path to the clinical data directory
        dest_dir: path to the BIDS directory
        subjs_list: subject list

    """
    import pandas as pd
    from os import path
    from clinica.utils.stream import cprint

    if subjs_list is None:
        adni_merge_path = path.join(csv_dir, 'ADNIMERGE.csv')
        adni_merge = pd.io.parsers.read_csv(adni_merge_path, sep=',')
        subjs_list = list(adni_merge.PTID.unique())

    cprint('Calculating paths of AV45 PET images. Output will be stored in ' + path.join(dest_dir, 'conversion_info') + '.')
    images = compute_av45_pet_paths(source_dir, csv_dir, dest_dir, subjs_list)
    cprint('Paths of AV45 PET images found. Exporting images into BIDS ...')
    av45_pet_paths_to_bids(images, dest_dir)
    cprint('AV45 PET conversion done.')


def compute_av45_pet_paths(source_dir, csv_dir, dest_dir, subjs_list):
    """
    Compute the paths to the all PET images and store them in a tsv file

    Args:
        source_dir: path to the original ADNI folder
        csv_dir: path to clinical data folder
        dest_dir: path to the BIDS folder
        subjs_list: subjects list

    Returns:
        images: a dataframe with all the paths to the PET images that will be converted into BIDS

    """
    import pandas as pd
    import os
    import operator
    from os import walk, path
    from numpy import argsort
    from clinica.iotools.converters.adni_to_bids.adni_utils import replace_sequence_chars
    from clinica.utils.stream import cprint
    from functools import reduce

    pet_av45_col = [
            'Subject_ID', 'VISCODE', 'Visit',
            'Sequence', 'Scan_Date', 'Study_ID',
            'Series_ID', 'Image_ID', 'Original'
            ]

    pet_av45_df = pd.DataFrame(columns=pet_av45_col)
    av45qc_path = path.join(csv_dir, 'AV45QC.csv')
    pet_meta_list_path = path.join(csv_dir, 'PET_META_LIST.csv')
    petqc = pd.io.parsers.read_csv(av45qc_path, sep=',')
    pet_meta_list = pd.io.parsers.read_csv(pet_meta_list_path, sep=',')

    for subj in subjs_list:
        pet_qc_subj = petqc[(petqc.PASS == 1) & (petqc.RID == int(subj[-4:]))]
        subject_pet_meta = pet_meta_list[pet_meta_list['Subject'] == subj]
        if subject_pet_meta.shape[0] < 1:
            # TODO Log somewhere subjects with problems
            cprint('NO Screening: Subject - ' + subj)
            continue

        for visit in list(pet_qc_subj.VISCODE2.unique()):
            pet_qc_visit = pet_qc_subj[pet_qc_subj.VISCODE2 == visit]
            if pet_qc_visit.shape[0] > 1:
                normal_images = []
                normal_meta = []
                for row in pet_qc_visit.iterrows():
                    image = row[1]
                    pet_meta_image = \
                        subject_pet_meta[(subject_pet_meta['Image ID'] == int(image.LONIUID[1:]))].iloc[0]
                    if pet_meta_image.Sequence.lower().find('early') < 0:
                        normal_images.append(image)
                        normal_meta.append(pet_meta_image)
                if len(normal_images) == 0:
                    # TODO Log somewhere subjects with problems
                    cprint('No regular AV45-PET image: Subject - ' + subj + ' for visit ' + visit)
                    continue
                if len(normal_images) == 1:
                    qc_visit = normal_images[0]
                else:
                    qc_visit = None
                    index = argsort([x['Series ID'] for x in normal_meta])
                    for i in index[::-1]:
                        coreg_avg = subject_pet_meta[(subject_pet_meta['Sequence'] == 'AV45 Co-registered, Averaged')
                                                     & (
                                                         subject_pet_meta['Series ID'] == normal_meta[i][
                                                             'Series ID'])]
                        if coreg_avg.shape[0] > 0:
                            qc_visit = normal_images[i]
                            break
                    if qc_visit is None:
                        qc_visit = normal_images[index[len(index) - 1]]
            else:
                qc_visit = pet_qc_visit.iloc[0]
            int_image_id = int(qc_visit.LONIUID[1:])
            original_pet_meta = subject_pet_meta[
                (subject_pet_meta['Orig/Proc'] == 'Original') & (subject_pet_meta['Image ID'] == int_image_id)
                & (subject_pet_meta.Sequence.map(lambda s: (s.lower().find('early') < 0)))]
            if original_pet_meta.shape[0] < 1:
                original_pet_meta = subject_pet_meta[
                        (subject_pet_meta['Orig/Proc'] == 'Original')
                        & (subject_pet_meta.Sequence.map(
                            lambda x: (x.lower().find('av45') > -1) & (x.lower().find('early') < 0))
                           )
                        & (subject_pet_meta['Scan Date'] == qc_visit.EXAMDATE)]
                if original_pet_meta.shape[0] < 1:
                    # TODO Log somewhere subjects with problems
                    cprint('NO Screening: Subject - ' + subj + ' for visit ' + qc_visit.VISCODE2)
                    continue
            original_image = original_pet_meta.iloc[0]
            averaged_pet_meta = subject_pet_meta[(subject_pet_meta['Sequence'] == 'AV45 Co-registered, Averaged') & (
                subject_pet_meta['Series ID'] == original_image['Series ID'])]
            if averaged_pet_meta.shape[0] < 1:
                sel_image = original_image
                original = True
            else:
                sel_image = averaged_pet_meta.iloc[0]
                original = False
            visit = sel_image.Visit
            sequence = replace_sequence_chars(sel_image.Sequence)
            date = sel_image['Scan Date']
            study_id = sel_image['Study ID']
            series_id = sel_image['Series ID']
            image_id = sel_image['Image ID']

            row_to_append = pd.DataFrame(
                [[subj, qc_visit.VISCODE2, str(visit), sequence, date, str(study_id), str(series_id), str(image_id),
                  original]],
                columns=pet_av45_col)
            pet_av45_df = pet_av45_df.append(row_to_append, ignore_index=True)

    # Exceptions
    # ==========
    conversion_errors = [  # Eq_1
                         ('128_S_2220', 'm48')]

    error_indices = []
    for conv_error in conversion_errors:
        error_indices.append((pet_av45_df.Subject_ID == conv_error[0])
                             & (pet_av45_df.VISCODE == conv_error[1]))

    indices_to_remove = pet_av45_df.index[reduce(operator.or_, error_indices, False)]
    pet_av45_df.drop(indices_to_remove, inplace=True)

    images = pet_av45_df
    # count = 0
    # total = images.shape[0]
    is_dicom = []
    image_folders = []
    for row in images.iterrows():
        image = row[1]
        seq_path = path.join(source_dir, str(image.Subject_ID), image.Sequence)
        # count += 1
        # print 'Processing Subject ' + str(image.Subject_ID) + ' - Session ' + image.VISCODE + ', ' + str(
        #     count) + ' / ' + str(total)
        image_path = ''
        for (dirpath, dirnames, filenames) in walk(seq_path):
            found = False
            for d in dirnames:
                if d == 'I' + str(image.Image_ID):
                    image_path = path.join(dirpath, d)
                    found = True
                    break
            if found:
                break

        dicom = True
        for (dirpath, dirnames, filenames) in walk(image_path):
            for f in filenames:
                if f.endswith(".nii"):
                    dicom = False
                    image_path = path.join(dirpath, f)
                    break

        is_dicom.append(dicom)
        image_folders.append(image_path)
        if image_path == '':
            cprint('Not found ' + str(image.Subject_ID))

    images.loc[:, 'Is_Dicom'] = pd.Series(is_dicom, index=images.index)
    images.loc[:, 'Path'] = pd.Series(image_folders, index=images.index)

    av45_csv_path = path.join(dest_dir, 'conversion_info')
    if not os.path.exists(av45_csv_path):
        os.mkdir(av45_csv_path)
    images.to_csv(path.join(av45_csv_path, 'av45_pet_paths.tsv'), sep='\t', index=False)
    return images


def av45_pet_paths_to_bids(images, bids_dir, dcm2niix="dcm2niix", dcm2nii="dcm2nii", mod_to_update=False):
    """
    Read the paths generated by the method compute_av45_pet and convert the original images to the BIDS standard

    Args:
        images: the dataframe returned by the method compute_av45_pet
        bids_dir: path to the BIDS directory
        dcm2niix: path to the dcm2niix tool (not useful anymore)
        dcm2nii: path to the dcm2nii tool (not useful anymore

    """
    import os
    import glob
    from numpy import nan
    from clinica.iotools.converters.adni_to_bids import adni_utils
    from clinica.utils.stream import cprint

    count = 0
    total = images.shape[0]

    for row in images.iterrows():
        image = row[1]
        subject = image.Subject_ID
        count += 1

        if image.Path is nan:
            cprint('No path specified for ' + image.Subject_ID + ' in session ' + image.VISCODE)
            continue

        cprint('Processing subject ' + str(subject) + ' - session ' + image.VISCODE + ', ' + str(count) + ' / ' + str(total))

        session = adni_utils.viscode_to_session(image.VISCODE)
        image_path = image.Path

        # ADDED lines
        # ------------------
        image_id = image.Image_ID
        # If the original image is a DICOM, check if contains two DICOM inside the same folder
        if image.Is_Dicom:
            image_path = adni_utils.check_two_dcm_folder(image_path, bids_dir, image_id)
        # ------------------

        bids_subj = subject.replace('_', '')
        output_path = os.path.join(bids_dir, 'sub-ADNI' + bids_subj + '/ses-' + session + '/pet')
        output_filename = 'sub-ADNI' + bids_subj + '_ses-' + session + '_task-rest_acq-av45_pet'

        # ADDED lines
        # ------------------
        # If updated mode is selected, check if an old AV45 image is existing and remove it
        existing_av45 = glob.glob(os.path.join(output_path, output_filename + '*'))
        if mod_to_update and len(existing_av45) > 0:
            cprint('Removing the old AV45 image...')
            for av45 in existing_av45:
                os.remove(av45)
                # ------------------

        try:
            os.makedirs(output_path)
        except OSError:
            if not os.path.isdir(output_path):
                raise

        if not image.Is_Dicom:
            adni_utils.center_nifti_origin(image_path, os.path.join(output_path, output_filename + '.nii.gz'))
        else:
            command = dcm2niix + ' -b n -z n -o ' + output_path + ' -f ' + output_filename + ' ' + image_path
            os.system(command)
            nifti_file = os.path.join(output_path, output_filename + '.nii')
            output_image = nifti_file + '.gz'

            # Check if conversion worked (output file exists?)
            if not os.path.isfile(nifti_file):
                cprint('Conversion with dcm2niix failed, trying with dcm2nii')
                command = dcm2nii + ' -a n -d n -e n -i y -g n -p n -m n -r n -x n -o ' + output_path + ' ' + image_path
                os.system(command)
                nifti_file = os.path.join(output_path, subject.replace('_', '') + '.nii')
                output_image = os.path.join(output_path, output_filename + '.nii.gz')

                if not os.path.isfile(nifti_file):
                    cprint('DICOM to NIFTI conversion error for ' + image_path)
                    continue

            adni_utils.center_nifti_origin(nifti_file, output_image)
            os.remove(nifti_file)

    adni_utils.remove_tmp_dmc_folder(bids_dir)

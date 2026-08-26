/*
 * Copyright 2026
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */

#include <pybind11/pybind11.h>

namespace py = pybind11;

#include <gnuradio/doa/MUSIC_uca.h>
#include "docstrings/MUSIC_uca_pydoc_template.h"

void bind_MUSIC_uca(py::module& m)
{
    using MUSIC_uca = ::gr::doa::MUSIC_uca;

    py::class_<MUSIC_uca,
               gr::sync_block,
               gr::block,
               gr::basic_block,
               std::shared_ptr<MUSIC_uca>>(m, "MUSIC_uca", D(MUSIC_uca))
        .def(py::init(&MUSIC_uca::make),
             py::arg("norm_radius"),
             py::arg("num_targets"),
             py::arg("inputs"),
             py::arg("pspectrum_len"),
             py::arg("element0_angle_deg"),
             py::arg("element_angle_step_deg"),
             D(MUSIC_uca, make));
}

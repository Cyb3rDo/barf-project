# Copyright (c) 2014, Fundacion Dr. Manuel Sadosky
# All rights reserved.

# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:

# 1. Redistributions of source code must retain the above copyright notice, this
# list of conditions and the following disclaimer.

# 2. Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.

# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""
Binary Interface Module.
"""

import logging

from elftools.elf.elffile import ELFFile
from pefile import PE

import barf.arch as arch

logger = logging.getLogger(__name__)


class Memory(object):

    def __init__(self):
        # List of virtual memory areas, tuple of (address, data)
        self.__vma = []

    def add_vma(self, address, data):
        self.__vma.append((address, data))

    def __iter__(self):
        for address, data in self.__vma:
            for i in xrange(len(data)):
                yield address + i

    def __getitem__(self, key):
        # TODO: Return bytearray or byte instead of str.
        if isinstance(key, slice):
            chunck = bytearray()

            step = 1 if key.step is None else key.step

            try:
                # Read memory one byte at a time.
                for addr in range(key.start, key.stop, step):
                    chunck.append(self._read_byte(addr))
            except IndexError as reason:
                logger.warn("Address out of range: {:#x}".format(addr))
                raise IndexError(reason)

            return str(chunck)
        elif isinstance(key, int):
            return str(self._read_byte(key))
        else:
            raise TypeError("Invalid argument type: {}".format(type(key)))

    def _read_byte(self, index):
        for address, data in self.__vma:
            if 0 <= index - address < len(data):
                return data[index - address]

        # If not in range raise an exception.
        raise IndexError

    @property
    def start(self):
        return min([address for address, _ in self.__vma])

    @property
    def end(self):
        return max([address + len(data) for address, data in self.__vma])


class BinaryFile(object):

    """Binary file representation.
    """

    def __init__(self, filename):

        # File name of the binary file.
        self._filename = filename

        # Section .text.
        self._section_text = None

        # Start address of the section .text.
        self._section_text_start = None

        # End address of the section .text (last addressable byte
        # address).
        self._section_text_end = None

        # Underlying architecture.
        self._arch = None

        # Architecture mode.
        self._arch_mode = None

        # Entry Point.
        self._entry_point = None

        # Open file
        if filename:
            self._open(filename)

    @property
    def ea_start(self):
        """Get start address of section .text.
        """
        return self._section_text_start

    @property
    def ea_end(self):
        """Get end address of section .text (last addressable byte
        address).

        """
        return self._section_text_end

    @property
    def architecture(self):
        """Get architecture name.
        """
        return self._arch

    @property
    def architecture_mode(self):
        """Get architecture mode name.
        """
        return self._arch_mode

    @property
    def filename(self):
        """Get file name.
        """
        return self._filename

    @property
    def file_format(self):
        """Get file format.
        """
        pass

    @property
    def text_section(self):
        """Get section .text.
        """
        return self._section_text_memory

    @property
    def entry_point(self):
        """Get entry point.
        """
        return self._entry_point

    def _open(self, filename):
        try:
            fd = open(filename, 'rb')
            signature = fd.read(4)
            fd.close()
        except:
            raise Exception("Error loading file: {}".format(filename))

        if signature[:4] == "\x7f\x45\x4c\x46":
            self._open_elf(filename)
        elif signature[:2] == b'\x4d\x5a':
            self._open_pe(filename)
        else:
            raise Exception("Unkown file format: {}".format(filename))

    def _open_elf(self, filename):
        f = open(filename, 'rb')

        elffile = ELFFile(f)

        self._entry_point = elffile.header['e_entry']
        self._arch = self._get_arch_elf(elffile)
        self._arch_mode = self._get_arch_mode_elf(elffile)

        # TODO: Load all segments instead of just one section.
        # Map binary to memory (only text section)
        m = Memory()

        for nseg, section in enumerate(elffile.iter_sections()):
            if section.name == ".text":
                text_section_start = section.header.sh_addr
                text_section_end = section.header.sh_addr + section.header.sh_size

                m.add_vma(section.header.sh_addr, bytearray(section.data()))

        # for nseg, segment in enumerate(elffile.iter_segments()):
        #     print("loading segment #{} - {} [{} bytes]".format(nseg, segment.header.p_vaddr, len(segment.data())))

        #     if len(segment.data()) > 0:
        #         m.add_vma(segment.header.p_vaddr, bytearray(segment.data()))

        f.close()

        self._section_text_start = text_section_start
        self._section_text_end = text_section_end - 1
        self._section_text_memory = m

    def _open_pe(self, filename):
        pe = pefile.PE(filename)

        pe.parse_data_directories()

        self._entry_point = pe.OPTIONAL_HEADER.ImageBase + pe.OPTIONAL_HEADER.AddressOfEntryPoint
        self._arch = self._get_arch_pe(elffile.get_machine_arch())
        self._arch_mode = self._get_arch_mode_pe(elffile.get_machine_arch())

        # TODO: Load all sections instead of just one.
        # Map binary to memory (only text section)
        m = Memory()

        section_idx = None

        for idx, section in enumerate(pe.sections):
            if section.Name.replace("\x00", ' ').strip() == ".text":
                section_idx = idx
                break

        if section_idx != None:
            section = pe.sections[section_idx]

            section_text_start = pe.OPTIONAL_HEADER.ImageBase + section.VirtualAddress
            section_text_end = self._section_text_start + len(section.get_data())

            m.add_vma(pe.OPTIONAL_HEADER.ImageBase + section.VirtualAddress, bytearray(section.get_data()))
        else:
            raise Exception("Error loading PE file.")

        # for idx, section in enumerate(pe.sections):
        #     print(section.Name)

        #     m.add_vma(pe.OPTIONAL_HEADER.ImageBase + section.VirtualAddress, bytearray(section.get_data()))

        pe.close()

        self._section_text_start = text_section_start
        self._section_text_end = text_section_end - 1
        self._section_text_memory = m

    def _get_arch_elf(self, elf_file):
        if elf_file.header['e_machine'] == 'EM_X86_64':
            return arch.ARCH_X86
        elif elf_file.header['e_machine'] in ('EM_386', 'EM_486'):
            return arch.ARCH_X86
        elif elf_file.header['e_machine'] == 'EM_ARM':
            return arch.ARCH_ARM
        else:
            raise Exception("Machine not supported.")

    def _get_arch_mode_elf(self, elf_file):
        if elf_file.header['e_machine'] == 'EM_X86_64':
            return arch.ARCH_X86_MODE_64
        elif elf_file.header['e_machine'] in ('EM_386', 'EM_486'):
            return arch.ARCH_X86_MODE_32
        elif elf_file.header['e_machine'] == 'EM_ARM':
            return arch.ARCH_ARM_MODE_ARM
        else:
            raise Exception("Machine not supported.")

    def _get_arch_pe(self, pe_file):
        # get arch
        if pe_file.FILE_HEADER.Machine == pefile.MACHINE_TYPE['IMAGE_FILE_MACHINE_I386']:
            return arch.ARCH_X86
        elif pe_file.FILE_HEADER.Machine == pefile.MACHINE_TYPE['IMAGE_FILE_MACHINE_AMD64']:
            return  arch.ARCH_X86
        elif pe_file.FILE_HEADER.Machine == pefile.MACHINE_TYPE['IMAGE_FILE_MACHINE_ARM']:
            return arch.ARCH_ARM
        elif pe_file.FILE_HEADER.Machine == pefile.MACHINE_TYPE['IMAGE_FILE_MACHINE_THUMB']:
            return arch.ARCH_ARM
        else:
            raise Exception("Machine not supported.")

    def _get_arch_mode_pe(self, pe_file):
        # get arch mode
        if pe_file.FILE_HEADER.Machine == pefile.MACHINE_TYPE['IMAGE_FILE_MACHINE_I386']:
            return arch.ARCH_X86_MODE_32
        elif pe_file.FILE_HEADER.Machine == pefile.MACHINE_TYPE['IMAGE_FILE_MACHINE_AMD64']:
            return arch.ARCH_X86_MODE_64
        elif pe_file.FILE_HEADER.Machine == pefile.MACHINE_TYPE['IMAGE_FILE_MACHINE_ARM']:
            return arch.ARCH_ARM_MODE_ARM
        elif pe_file.FILE_HEADER.Machine == pefile.MACHINE_TYPE['IMAGE_FILE_MACHINE_THUMB']:
            return arch.ARCH_ARM_MODE_THUMB
        else:
            raise Exception("Machine not supported.")

    def _map_architecture(self, bfd_arch_name):
        arch_map = {
            "Intel 386" : arch.ARCH_X86,
            "ARM"       : arch.ARCH_ARM,
        }

        return arch_map[bfd_arch_name]

    def _map_architecture_mode(self, bfd_arch_name, bfd_arch_size):
        arch_mode_map = {
            "Intel 386" : {
                32 : arch.ARCH_X86_MODE_32,
                64 : arch.ARCH_X86_MODE_64
            },
            # TODO: Distinguish between ARM or THUMB state.
            "ARM" : {
                32 : None,
            },
        }

        return arch_mode_map[bfd_arch_name][bfd_arch_size]

    def _text_section_reader(self, address, size):
        start = address - self._section_text_start
        end = start + size

        return self._section_text[start:end]

    def _text_section_writer(self):
        raise Exception("section .text is readonly.")
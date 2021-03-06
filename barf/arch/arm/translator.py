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

import logging

import barf.arch.arm.translators as translators

from barf.arch import ARCH_ARM_MODE_ARM
from barf.arch import ARCH_ARM_MODE_THUMB
from barf.arch.arm import ARM_COND_CODE_AL
from barf.arch.arm import ARM_COND_CODE_CC
from barf.arch.arm import ARM_COND_CODE_CS
from barf.arch.arm import ARM_COND_CODE_EQ
from barf.arch.arm import ARM_COND_CODE_GE
from barf.arch.arm import ARM_COND_CODE_GT
from barf.arch.arm import ARM_COND_CODE_HI
from barf.arch.arm import ARM_COND_CODE_HS
from barf.arch.arm import ARM_COND_CODE_LE
from barf.arch.arm import ARM_COND_CODE_LO
from barf.arch.arm import ARM_COND_CODE_LS
from barf.arch.arm import ARM_COND_CODE_LT
from barf.arch.arm import ARM_COND_CODE_MI
from barf.arch.arm import ARM_COND_CODE_NE
from barf.arch.arm import ARM_COND_CODE_PL
from barf.arch.arm import ARM_COND_CODE_VC
from barf.arch.arm import ARM_COND_CODE_VS
from barf.arch.arm import ARM_MEMORY_INDEX_OFFSET
from barf.arch.arm import ARM_MEMORY_INDEX_POST
from barf.arch.arm import ARM_MEMORY_INDEX_PRE
from barf.arch.arm import ArmArchitectureInformation
from barf.arch.arm import ArmImmediateOperand
from barf.arch.arm import ArmMemoryOperand
from barf.arch.arm import ArmRegisterListOperand
from barf.arch.arm import ArmRegisterOperand
from barf.arch.arm import ArmShiftedRegisterOperand
from barf.arch.translator import TranslationBuilder
from barf.arch.translator import Translator
from barf.core.reil import ReilImmediateOperand
from barf.core.reil import ReilRegisterOperand
from barf.core.reil.builder import ReilBuilder
from barf.utils.utils import VariableNamer

logger = logging.getLogger(__name__)


class ArmTranslationBuilder(TranslationBuilder):

    def __init__(self, ir_name_generator, architecture_mode):
        super(ArmTranslationBuilder, self).__init__(ir_name_generator, ArmArchitectureInformation(architecture_mode))

    def read(self, arm_operand):

        if isinstance(arm_operand, ArmImmediateOperand):

            reil_operand = ReilImmediateOperand(arm_operand.immediate, arm_operand.size)

        elif isinstance(arm_operand, ArmRegisterOperand):

            reil_operand = ReilRegisterOperand(arm_operand.name, arm_operand.size)

        elif isinstance(arm_operand, ArmShiftedRegisterOperand):

            reil_operand = self._compute_shifted_register(arm_operand)

        elif isinstance(arm_operand, ArmMemoryOperand):

            addr = self._compute_memory_address(arm_operand)

            reil_operand = self.temporal(arm_operand.size)

            self.add(self._builder.gen_ldm(addr, reil_operand))

        elif isinstance(arm_operand, ArmRegisterListOperand):

            reil_operand = self._compute_register_list(arm_operand)

        else:
            raise NotImplementedError("Instruction Not Implemented: Unknown operand for read operation.")

        return reil_operand

    def write(self, arm_operand, value):

        if isinstance(arm_operand, ArmRegisterOperand):

            reil_operand = ReilRegisterOperand(arm_operand.name, arm_operand.size)

            self.add(self._builder.gen_str(value, reil_operand))

        elif isinstance(arm_operand, ArmMemoryOperand):

            addr = self._compute_memory_address(arm_operand)

            self.add(self._builder.gen_stm(value, addr))

        else:
            raise NotImplementedError("Instruction Not Implemented: Unknown operand for write operation.")

    def _compute_shifted_register(self, sh_op):

        base = ReilRegisterOperand(sh_op.base_reg.name, sh_op.size)

        if sh_op.shift_amount:
            ret = self.temporal(sh_op.size)

            if isinstance(sh_op.shift_amount, ArmImmediateOperand):
                sh_am = ReilImmediateOperand(sh_op.shift_amount.immediate, sh_op.size)
            elif isinstance(sh_op.shift_amount, ArmRegisterOperand):
                sh_am = ReilRegisterOperand(sh_op.shift_amount.name, sh_op.shift_amount.size)
            else:
                raise NotImplementedError("Instruction Not Implemented: Unknown shift amount type.")

            if sh_op.shift_type == 'lsl':
                if isinstance(sh_am, ReilImmediateOperand):
                    self.add(self._builder.gen_bsh(base, sh_am, ret))
                else:
                    sh_am_greater_32_label = self.label('sh_am_greater_32_label')
                    sh_am_end_label = self.label('sh_am_end_label')

                    sh_am_7_0 = self._and_regs(sh_am, self.immediate(0xFF, sh_am.size))

                    self.add(self._builder.gen_jcc(self._greater_than_or_equal(sh_am_7_0, self.immediate(33, sh_am_7_0.size)),
                                                 sh_am_greater_32_label))

                    # Shift < 32 => shifted_register = base lsl sh_am
                    self.add(self._builder.gen_bsh(base, sh_am_7_0, ret))
                    self._jump_to(sh_am_end_label)

                    # Shift >= 32 => shifted_register = 0
                    self.add(sh_am_greater_32_label)
                    self.add(self._builder.gen_str(self.immediate(0x0, ret.size), ret))

                    self.add(sh_am_end_label)
            else:
                # TODO: Implement other shift types
                raise NotImplementedError("Instruction Not Implemented: Shift type.")
        else:
            ret = base

        return ret

    def _compute_memory_address(self, mem_operand):
        """Return operand memory access translation.
        """
        base = ReilRegisterOperand(mem_operand.base_reg.name, mem_operand.size)

        if mem_operand.displacement:
            address = self.temporal(mem_operand.size)

            if isinstance(mem_operand.displacement, ArmRegisterOperand):
                disp = ReilRegisterOperand(mem_operand.displacement.name, mem_operand.size)
            elif isinstance(mem_operand.displacement, ArmImmediateOperand):
                disp = ReilImmediateOperand(mem_operand.displacement.immediate, mem_operand.size)
            elif isinstance(mem_operand.displacement, ArmShiftedRegisterOperand):
                disp = self._compute_shifted_register(mem_operand.displacement)
            else:
                raise Exception("_compute_memory_address: displacement type unknown")

            if mem_operand.index_type == ARM_MEMORY_INDEX_PRE:
                if mem_operand.disp_minus:
                    self.add(self._builder.gen_sub(base, disp, address))
                else:
                    self.add(self._builder.gen_add(base, disp, address))
                self.add(self._builder.gen_str(address, base))
            elif mem_operand.index_type == ARM_MEMORY_INDEX_OFFSET:
                if mem_operand.disp_minus:
                    self.add(self._builder.gen_sub(base, disp, address))
                else:
                    self.add(self._builder.gen_add(base, disp, address))
            elif mem_operand.index_type == ARM_MEMORY_INDEX_POST:
                self.add(self._builder.gen_str(base, address))
                tmp = self.temporal(base.size)
                if mem_operand.disp_minus:
                    self.add(self._builder.gen_sub(base, disp, tmp))
                else:
                    self.add(self._builder.gen_add(base, disp, tmp))
                self.add(self._builder.gen_str(tmp, base))
            else:
                raise Exception("_compute_memory_address: indexing type unknown")

        else:
            address = base

        return address

    def _compute_register_list(self, operand):
        """Return operand register list.
        """

        ret = []
        for reg_range in operand.reg_list:
            if len(reg_range) == 1:
                ret.append(ReilRegisterOperand(reg_range[0].name, reg_range[0].size))
            else:
                reg_num = int(reg_range[0].name[1:])    # Assuming the register is named with one letter + number
                reg_end = int(reg_range[1].name[1:])
                if reg_num > reg_end:
                    raise NotImplementedError("Instruction Not Implemented: Invalid register range.")
                while reg_num <= reg_end:
                    ret.append(ReilRegisterOperand(reg_range[0].name[0] + str(reg_num), reg_range[0].size))
                    reg_num = reg_num + 1

        return ret


class ArmTranslator(Translator):

    """ARM to IR Translator."""

    def __init__(self, architecture_mode=ARCH_ARM_MODE_THUMB):
        super(ArmTranslator, self).__init__()

        # Set *Architecture Mode*. The translation of each instruction
        # into the REIL language is based on this.
        self._arch_mode = architecture_mode

        # An instance of *ArchitectureInformation*.
        self._arch_info = ArmArchitectureInformation(architecture_mode)

        # An instance of a *VariableNamer*. This is used so all the
        # temporary REIL registers are unique.
        self._ir_name_generator = VariableNamer("t", separator="")

        self._builder = ReilBuilder()

        self._flags = {
            "nf": ReilRegisterOperand("nf", 1),
            "zf": ReilRegisterOperand("zf", 1),
            "cf": ReilRegisterOperand("cf", 1),
            "vf": ReilRegisterOperand("vf", 1),
        }

        if self._arch_mode in [ARCH_ARM_MODE_ARM, ARCH_ARM_MODE_THUMB]:
            self._sp = ReilRegisterOperand("r13", 32)   # TODO: Implement alias
            self._pc = ReilRegisterOperand("r15", 32)
            self._lr = ReilRegisterOperand("r14", 32)

            self._ws = ReilImmediateOperand(4, 32)      # word size

    def translate(self, instruction):
        """Return IR representation of an instruction.
        """
        try:
            trans_instrs = self.__translate(instruction)
        except NotImplementedError as e:
            unkn_instr = self._builder.gen_unkn()
            unkn_instr.address = instruction.address << 8 | (0x0 & 0xff)
            trans_instrs = [unkn_instr]

            self.__log_not_supported_instruction(instruction, str(e))
        except Exception:
            self.__log_translation_exception(instruction)

            raise

        return trans_instrs

    def reset(self):
        """Restart IR register name generator.
        """
        self._ir_name_generator.reset()

    def __translate(self, instruction):
        """Translate a arm instruction into REIL language.

        :param instruction: a arm instruction
        :type instruction: ArmInstruction
        """

        # Retrieve translation function.
        mnemonic = instruction.mnemonic

        tb = ArmTranslationBuilder(self._ir_name_generator, self._arch_mode)

        # TODO: Improve this.
        if instruction.mnemonic in ["b", "bl", "bx", "blx", "bne", "beq", "bpl",
                                    "ble", "bcs", "bhs", "blt", "bge", "bhi",
                                    "blo", "bls"]:
            if instruction.condition_code is None:
                instruction.condition_code = ARM_COND_CODE_AL  # TODO: unify translations
        else:
            # Pre-processing: evaluate flags
            if instruction.condition_code is not None:
                self._evaluate_condition_code(tb, instruction)

        # Translate instruction.
        if mnemonic in translators.dispatcher:
            translators.dispatcher[mnemonic](self, tb, instruction)
        else:
            raise NotImplementedError("Instruction Not Implemented")

        return tb.instanciate(instruction.address)

    def __log_not_supported_instruction(self, instruction, reason="unknown"):
        bytes_str = " ".join("%02x" % ord(b) for b in instruction.bytes)

        logger.info(
            "Instruction not supported: %s (%s [%s]). Reason: %s",
            instruction.mnemonic,
            instruction,
            bytes_str,
            reason
        )

    def __log_translation_exception(self, instruction):
        bytes_str = " ".join("%02x" % ord(b) for b in instruction.bytes)

        logger.error(
            "Failed to translate arm to REIL: %s (%s)",
            instruction,
            bytes_str,
            exc_info=True
        )

    # Flag translation.
    # ======================================================================== #
    def _update_nf(self, tb, oprnd0, oprnd1, result):
        sign = tb._extract_bit(result, oprnd0.size - 1)
        tb.add(self._builder.gen_str(sign, self._flags["nf"]))

    def _carry_from_uf(self, tb, oprnd0, oprnd1, result):
        assert (result.size == oprnd0.size * 2)

        carry = tb._extract_bit(result, oprnd0.size)
        tb.add(self._builder.gen_str(carry, self._flags["cf"]))

    def _borrow_from_uf(self, tb, oprnd0, oprnd1, result):
        # BorrowFrom as defined in the ARM Reference Manual has the same implementation as CarryFrom
        self._carry_from_uf(tb, oprnd0, oprnd1, result)

    def _overflow_from_add_uf(self, tb, oprnd0, oprnd1, result):
        op1_sign = tb._extract_bit(oprnd0, oprnd0.size - 1)
        op2_sign = tb._extract_bit(oprnd1, oprnd0.size - 1)
        res_sign = tb._extract_bit(result, oprnd0.size - 1)

        overflow = tb._and_regs(tb._equal_regs(op1_sign, op2_sign), tb._unequal_regs(op1_sign, res_sign))
        tb.add(self._builder.gen_str(overflow, self._flags["vf"]))

    def _overflow_from_sub_uf(self, tb, oprnd0, oprnd1, result):
        # Evaluate overflow and update the flag
        tb.add(self._builder.gen_str(tb._overflow_from_sub(oprnd0, oprnd1, result), self._flags["vf"]))

    def _update_zf(self, tb, oprnd0, oprnd1, result):
        zf = self._flags["zf"]

        imm0 = tb.immediate((2**oprnd0.size)-1, result.size)

        tmp0 = tb.temporal(oprnd0.size)

        tb.add(self._builder.gen_and(result, imm0, tmp0))  # filter low part of result
        tb.add(self._builder.gen_bisz(tmp0, zf))

    def _carry_out(self, tb, carry_operand, oprnd0, oprnd1, result):
        if isinstance(carry_operand, ArmImmediateOperand):
            return
        elif isinstance(carry_operand, ArmRegisterOperand):
            return
        elif isinstance(carry_operand, ArmShiftedRegisterOperand):
            base = ReilRegisterOperand(carry_operand.base_reg.name, carry_operand.size)
            shift_type = carry_operand.shift_type
            shift_amount = carry_operand.shift_amount

            if shift_type == 'lsl':

                if isinstance(shift_amount, ArmImmediateOperand):
                    if shift_amount.immediate == 0:
                        return
                    else:
                        # carry_out = Rm[32 - shift_imm]
                        shift_carry_out = tb._extract_bit(base, 32 - shift_amount.immediate)

                elif isinstance(shift_amount, ArmRegisterOperand):
                    # Rs: register with shift amount
                    # if Rs[7:0] == 0 then
                    #     carry_out = C Flag
                    # else if Rs[7:0] <= 32 then
                    #     carry_out = Rm[32 - Rs[7:0]]
                    # else /* Rs[7:0] > 32 */
                    #     carry_out = 0

                    shift_carry_out = tb.temporal(1)
                    tb.add(self._builder.gen_str(self._flags["cf"], shift_carry_out))
                    rs = ReilRegisterOperand(shift_amount.name, shift_amount.size)
                    rs_7_0 = tb._and_regs(rs, tb.immediate(0xFF, rs.size))

                    end_label = tb.label('end_label')
                    rs_greater_32_label = tb.label('rs_greater_32_label')

                    # if Rs[7:0] == 0 then
                    #     carry_out = C Flag
                    tb._jump_if_zero(rs_7_0, end_label)     # shift_carry_out already has the C flag set, so do nothing

                    tb.add(self._builder.gen_jcc(tb._greater_than_or_equal(rs_7_0, tb.immediate(33, rs_7_0.size)),
                                                 rs_greater_32_label))

                    # Rs > 0 and Rs <= 32
                    #     carry_out = Rm[32 - Rs[7:0]]
                    extract_bit_number = tb.temporal(rs_7_0.size)
                    tb.add(self._builder.gen_sub(tb.immediate(32, rs_7_0.size), rs_7_0, extract_bit_number))
                    tb.add(self._builder.gen_str(tb._extract_bit_with_register(base, extract_bit_number),
                                                 shift_carry_out))
                    tb._jump_to(end_label)

                    # else /* Rs[7:0] > 32 */
                    #     carry_out = 0
                    tb.add(rs_greater_32_label)
                    tb.add(self._builder.gen_str(tb.immediate(0, 1), shift_carry_out))
                    # tb._jump_to(end_label)

                    tb.add(end_label)

                else:
                    raise Exception("carry_out: Unknown shift amount type.")

            else:
                # TODO: Implement other shift types
                raise NotImplementedError("Instruction Not Implemented: carry_out: shift type " + carry_operand.shift_type)

        else:
            raise Exception("carry_out: Unknown operand type.")

        tb.add(self._builder.gen_str(shift_carry_out, self._flags["cf"]))

    def _update_flags_data_proc_add(self, tb, oprnd0, oprnd1, result):
        self._update_zf(tb, oprnd0, oprnd1, result)
        self._update_nf(tb, oprnd0, oprnd1, result)
        self._carry_from_uf(tb, oprnd0, oprnd1, result)
        self._overflow_from_add_uf(tb, oprnd0, oprnd1, result)

    def _update_flags_data_proc_sub(self, tb, oprnd0, oprnd1, result):
        self._update_zf(tb, oprnd0, oprnd1, result)
        self._update_nf(tb, oprnd0, oprnd1, result)
        self._borrow_from_uf(tb, oprnd0, oprnd1, result)
        # C Flag = NOT BorrowFrom (to be used by subsequent instructions like SBC and RSC)
        tb.add(self._builder.gen_str(tb._negate_reg(self._flags["cf"]), self._flags["cf"]))
        self._overflow_from_sub_uf(tb, oprnd0, oprnd1, result)

    def _update_flags_data_proc_other(self, tb, second_operand, oprnd0, oprnd1, result):
        self._update_zf(tb, oprnd0, oprnd1, result)
        self._update_nf(tb, oprnd0, oprnd1, result)
        self._carry_out(tb, second_operand, oprnd0, oprnd1, result)
        # Overflow Flag (V) unaffected

    def _update_flags_other(self, tb, oprnd0, oprnd1, result):
        self._update_zf(tb, oprnd0, oprnd1, result)
        self._update_nf(tb, oprnd0, oprnd1, result)
        # Carry Flag (C) unaffected
        # Overflow Flag (V) unaffected

    def _undefine_flag(self, tb, flag):
        # NOTE: In every test I've made, each time a flag is leave
        # undefined it is always set to 0.

        imm = tb.immediate(0, flag.size)

        tb.add(self._builder.gen_str(imm, flag))

    def _clear_flag(self, tb, flag):
        imm = tb.immediate(0, flag.size)

        tb.add(self._builder.gen_str(imm, flag))

    def _set_flag(self, tb, flag):
        imm = tb.immediate(1, flag.size)

        tb.add(self._builder.gen_str(imm, flag))

    # Helpers.
    # ======================================================================== #
    def _evaluate_eq(self, tb):
        # EQ: Z set
        return self._flags["zf"]

    def _evaluate_ne(self, tb):
        # NE: Z clear
        return tb._negate_reg(self._flags["zf"])

    def _evaluate_cs(self, tb):
        # CS: C set
        return self._flags["cf"]

    def _evaluate_cc(self, tb):
        # CC: C clear
        return tb._negate_reg(self._flags["cf"])

    def _evaluate_mi(self, tb):
        # MI: N set
        return self._flags["nf"]

    def _evaluate_pl(self, tb):
        # PL: N clear
        return tb._negate_reg(self._flags["nf"])

    def _evaluate_vs(self, tb):
        # VS: V set
        return self._flags["vf"]

    def _evaluate_vc(self, tb):
        # VC: V clear
        return tb._negate_reg(self._flags["vf"])

    def _evaluate_hi(self, tb):
        # HI: C set and Z clear
        return tb._and_regs(self._flags["cf"], tb._negate_reg(self._flags["zf"]))

    def _evaluate_ls(self, tb):
        # LS: C clear or Z set
        return tb._or_regs(tb._negate_reg(self._flags["cf"]), self._flags["zf"])

    def _evaluate_ge(self, tb):
        # GE: N == V
        return tb._equal_regs(self._flags["nf"], self._flags["vf"])

    def _evaluate_lt(self, tb):
        # LT: N != V
        return tb._negate_reg(self._evaluate_ge(tb))

    def _evaluate_gt(self, tb):
        # GT: (Z == 0) and (N == V)
        return tb._and_regs(tb._negate_reg(self._flags["zf"]), self._evaluate_ge(tb))

    def _evaluate_le(self, tb):
        # LE: (Z == 1) or (N != V)
        return tb._or_regs(self._flags["zf"], self._evaluate_lt(tb))

    def _evaluate_condition_code(self, tb, instruction):
        if instruction.condition_code == ARM_COND_CODE_AL:
            return

        eval_cc_fn = {
            ARM_COND_CODE_EQ: self._evaluate_eq,
            ARM_COND_CODE_NE: self._evaluate_ne,
            ARM_COND_CODE_CS: self._evaluate_cs,
            ARM_COND_CODE_HS: self._evaluate_cs,
            ARM_COND_CODE_CC: self._evaluate_cc,
            ARM_COND_CODE_LO: self._evaluate_cc,
            ARM_COND_CODE_MI: self._evaluate_mi,
            ARM_COND_CODE_PL: self._evaluate_pl,
            ARM_COND_CODE_VS: self._evaluate_vs,
            ARM_COND_CODE_VC: self._evaluate_vc,
            ARM_COND_CODE_HI: self._evaluate_hi,
            ARM_COND_CODE_LS: self._evaluate_ls,
            ARM_COND_CODE_GE: self._evaluate_ge,
            ARM_COND_CODE_LT: self._evaluate_lt,
            ARM_COND_CODE_GT: self._evaluate_gt,
            ARM_COND_CODE_LE: self._evaluate_le,
        }

        neg_cond = tb._negate_reg(eval_cc_fn[instruction.condition_code](tb))

        end_addr = ReilImmediateOperand((instruction.address + instruction.size) << 8, self._arch_info.address_size + 8)

        tb.add(self._builder.gen_jcc(neg_cond, end_addr))

        return

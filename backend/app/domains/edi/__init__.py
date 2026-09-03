# EDI domain (P7.a Stage 2): documents that leave the platform for Didox and, through
# the roaming centre, for my.soliq.uz — «Договор НК» (007) and ЭСФ (002).
#
# It is its own context rather than a corner of `contracts/` or `deals/` because the
# ЭСФ belongs to a deal and the договор to a contract, and neither of those domains may
# own the other's document. `edi` references both by id and reacts to their events; it
# never imports their services, and they never import it.
#
# NOT here: the sample commitment letter (письмо-обязательство). That one is ours, signed
# with our own E-IMZO rails, and never leaves the platform — it lives in `lab_orders/`
# beside the sample request it belongs to.

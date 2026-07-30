import { useEffect, useMemo } from "react";

import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

import { ChevronLeftIcon, FlowHeader, IconButton, Stepper } from "@/shared/ui";
import type { Step } from "@/shared/ui";

import {
  LAB_STEP_DETAILS,
  LAB_STEP_LICENSES,
  LAB_STEP_REVIEW,
  LAB_STEP_TYPE,
  LOG_STEP_DETAILS,
  LOG_STEP_GEOGRAPHY,
  LOG_STEP_REVIEW,
  LOG_STEP_SERVICES,
  LOG_STEP_SPECIALIZATION,
  LOG_STEP_TARIFFS_DOCS,
  LOG_STEP_TYPE,
  MFR_STEP_BUYER,
  MFR_STEP_CATALOG,
  MFR_STEP_CERTIFICATES,
  MFR_STEP_DETAILS,
  MFR_STEP_PRODUCTION,
  MFR_STEP_REVIEW,
  MFR_STEP_TYPE,
  WIZARD_FIRST_STEP,
  WIZARD_STEP_BANK,
  WIZARD_STEP_DETAILS,
  WIZARD_STEP_DOCUMENTS,
  WIZARD_STEP_REVIEW,
  WIZARD_STEP_TYPE,
  isLaboratoryType,
  isLogisticsType,
  isManufacturerType,
  wizardStepCount,
} from "../model/constants";
import { useWizardDraft } from "../model/draftStore";
import {
  areDocumentsValid,
  isAccountTypeValid,
  isBankValid,
  isBuyerRequirementsValid,
  isIdentityValidForType,
  isLogisticsGeographyValid,
  isLogisticsServicesValid,
  isLogisticsSpecializationValid,
  isLogisticsTariffsValid,
  isProductionValid,
} from "../model/validation";
import { StepAccountType } from "./StepAccountType";
import { StepBank } from "./StepBank";
import { StepBuyerRequirements } from "./StepBuyerRequirements";
import { StepCatalog } from "./StepCatalog";
import { StepDetails } from "./StepDetails";
import { StepDocuments } from "./StepDocuments";
import { StepLabLicenses } from "./StepLabLicenses";
import { StepLogisticsGeography } from "./StepLogisticsGeography";
import { StepLogisticsServices } from "./StepLogisticsServices";
import { StepLogisticsSpecialization } from "./StepLogisticsSpecialization";
import { StepLogisticsTariffsDocs } from "./StepLogisticsTariffsDocs";
import { StepManufacturerCerts } from "./StepManufacturerCerts";
import { StepProduction } from "./StepProduction";
import { StepReview } from "./StepReview";

/**
 * URL-addressable company registration wizard, rendered full-screen.
 *
 * Step count and sheets branch on account type: manufacturers follow the
 * 7-step factory flow; logistics follow the 7-step carrier flow; laboratories
 * follow the lab flow from `labaratory_reg_flow.jpeg`; everyone else keeps the
 * shared 5-step path.
 */
export function CompanyWizard() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const params = useParams<{ step?: string }>();
  const draft = useWizardDraft();
  const manufacturer = isManufacturerType(draft.accountType);
  const logistics = isLogisticsType(draft.accountType);
  const laboratory = isLaboratoryType(draft.accountType);
  const stepCount = wizardStepCount(draft.accountType);

  const { completedIds, furthestAllowed } = useMemo(() => {
    if (manufacturer) {
      const satisfied: Array<[number, boolean]> = [
        [MFR_STEP_TYPE, isAccountTypeValid(draft.accountType) || draft.companyId != null],
        [MFR_STEP_DETAILS, isIdentityValidForType(draft.identity, draft.accountType)],
        [MFR_STEP_PRODUCTION, isProductionValid(draft.manufacturer)],
        [MFR_STEP_CATALOG, true],
        [
          MFR_STEP_CERTIFICATES,
          areDocumentsValid(draft.documents, draft.bank, draft.identityLocked, draft.accountType),
        ],
        [MFR_STEP_BUYER, isBuyerRequirementsValid(draft.manufacturer)],
      ];
      const done: number[] = [];
      for (const [id, ok] of satisfied) {
        if (!ok) break;
        done.push(id);
      }
      const last = done.at(-1);
      return {
        completedIds: done,
        furthestAllowed: last === undefined ? WIZARD_FIRST_STEP : last + 1,
      };
    }

    if (logistics) {
      const satisfied: Array<[number, boolean]> = [
        [LOG_STEP_TYPE, isAccountTypeValid(draft.accountType) || draft.companyId != null],
        [
          LOG_STEP_DETAILS,
          isIdentityValidForType(draft.identity, draft.accountType, draft.logistics),
        ],
        [LOG_STEP_SERVICES, isLogisticsServicesValid(draft.logistics)],
        [LOG_STEP_GEOGRAPHY, isLogisticsGeographyValid(draft.logistics)],
        [LOG_STEP_SPECIALIZATION, isLogisticsSpecializationValid(draft.logistics)],
        [
          LOG_STEP_TARIFFS_DOCS,
          isLogisticsTariffsValid(draft.logistics) &&
            areDocumentsValid(draft.documents, draft.bank, draft.identityLocked, draft.accountType),
        ],
      ];
      const done: number[] = [];
      for (const [id, ok] of satisfied) {
        if (!ok) break;
        done.push(id);
      }
      const last = done.at(-1);
      return {
        completedIds: done,
        furthestAllowed: last === undefined ? WIZARD_FIRST_STEP : last + 1,
      };
    }

    if (laboratory) {
      const satisfied: Array<[number, boolean]> = [
        [LAB_STEP_TYPE, isAccountTypeValid(draft.accountType) || draft.companyId != null],
        [
          LAB_STEP_DETAILS,
          isIdentityValidForType(
            draft.identity,
            draft.accountType,
            draft.logistics,
            draft.laboratory,
          ),
        ],
        [
          LAB_STEP_LICENSES,
          areDocumentsValid(draft.documents, draft.bank, draft.identityLocked, draft.accountType),
        ],
      ];
      const done: number[] = [];
      for (const [id, ok] of satisfied) {
        if (!ok) break;
        done.push(id);
      }
      const last = done.at(-1);
      return {
        completedIds: done,
        furthestAllowed: last === undefined ? WIZARD_FIRST_STEP : last + 1,
      };
    }

    const satisfied: Array<[number, boolean]> = [
      [WIZARD_STEP_TYPE, isAccountTypeValid(draft.accountType) || draft.companyId != null],
      [WIZARD_STEP_DETAILS, isIdentityValidForType(draft.identity, draft.accountType)],
      [WIZARD_STEP_BANK, isBankValid(draft.bank)],
      [
        WIZARD_STEP_DOCUMENTS,
        areDocumentsValid(draft.documents, draft.bank, draft.identityLocked, draft.accountType),
      ],
    ];
    const done: number[] = [];
    for (const [id, ok] of satisfied) {
      if (!ok) break;
      done.push(id);
    }
    const last = done.at(-1);
    return {
      completedIds: done,
      furthestAllowed: last === undefined ? WIZARD_FIRST_STEP : last + 1,
    };
  }, [draft, manufacturer, logistics, laboratory]);

  const requested = clampStep(params.step, stepCount);
  const step = Math.min(requested, furthestAllowed);

  useEffect(() => {
    if (String(step) !== params.step) {
      void navigate(`/companies/new/${step}`, { replace: true });
    }
  }, [step, params.step, navigate]);

  const goTo = (next: number): void => {
    void navigate(`/companies/new/${next}`);
  };

  const steps: Step[] = manufacturer
    ? [
        { id: MFR_STEP_TYPE, label: t("wizard.steps.accountType") },
        { id: MFR_STEP_DETAILS, label: t("wizard.steps.details") },
        { id: MFR_STEP_PRODUCTION, label: t("wizard.steps.production") },
        { id: MFR_STEP_CATALOG, label: t("wizard.steps.catalog") },
        { id: MFR_STEP_CERTIFICATES, label: t("wizard.steps.certificates") },
        { id: MFR_STEP_BUYER, label: t("wizard.steps.buyerReqs") },
        { id: MFR_STEP_REVIEW, label: t("wizard.steps.review") },
      ]
    : logistics
      ? [
          { id: LOG_STEP_TYPE, label: t("wizard.steps.accountType") },
          { id: LOG_STEP_DETAILS, label: t("wizard.steps.details") },
          { id: LOG_STEP_SERVICES, label: t("wizard.steps.services") },
          { id: LOG_STEP_GEOGRAPHY, label: t("wizard.steps.geography") },
          { id: LOG_STEP_SPECIALIZATION, label: t("wizard.steps.specialization") },
          { id: LOG_STEP_TARIFFS_DOCS, label: t("wizard.steps.tariffsDocs") },
          { id: LOG_STEP_REVIEW, label: t("wizard.steps.review") },
        ]
      : laboratory
        ? [
            { id: LAB_STEP_TYPE, label: t("wizard.steps.accountType") },
            { id: LAB_STEP_DETAILS, label: t("wizard.steps.details") },
            { id: LAB_STEP_LICENSES, label: t("wizard.steps.labLicenses") },
            { id: LAB_STEP_REVIEW, label: t("wizard.steps.review") },
          ]
        : [
            { id: WIZARD_STEP_TYPE, label: t("wizard.steps.accountType") },
            { id: WIZARD_STEP_DETAILS, label: t("wizard.steps.details") },
            { id: WIZARD_STEP_BANK, label: t("wizard.steps.bank") },
            { id: WIZARD_STEP_DOCUMENTS, label: t("wizard.steps.documents") },
            { id: WIZARD_STEP_REVIEW, label: t("wizard.steps.review") },
          ];

  const title = manufacturer
    ? t("wizard.manufacturerTitle")
    : logistics
      ? t("wizard.logisticsTitle")
      : laboratory
        ? t("wizard.laboratoryTitle")
        : t("wizard.title");

  return (
    <div className="space-y-6">
      <FlowHeader
        title={title}
        leading={
          <IconButton
            label={t("common.back")}
            onClick={() => (step > WIZARD_FIRST_STEP ? goTo(step - 1) : void navigate("/companies"))}
          >
            <ChevronLeftIcon size={20} />
          </IconButton>
        }
      />

      <Stepper steps={steps} current={step} completedIds={completedIds} variant="stacked" />

      <div className="pt-2">
        {step === WIZARD_STEP_TYPE ? (
          <StepAccountType onNext={() => goTo(WIZARD_STEP_DETAILS)} />
        ) : null}

        {manufacturer ? (
          <>
            {step === MFR_STEP_DETAILS ? (
              <StepDetails
                onNext={() => goTo(MFR_STEP_PRODUCTION)}
                onBack={() => goTo(MFR_STEP_TYPE)}
              />
            ) : null}
            {step === MFR_STEP_PRODUCTION ? (
              <StepProduction
                onNext={() => goTo(MFR_STEP_CATALOG)}
                onBack={() => goTo(MFR_STEP_DETAILS)}
              />
            ) : null}
            {step === MFR_STEP_CATALOG ? (
              <StepCatalog
                onNext={() => goTo(MFR_STEP_CERTIFICATES)}
                onBack={() => goTo(MFR_STEP_PRODUCTION)}
              />
            ) : null}
            {step === MFR_STEP_CERTIFICATES ? (
              <StepManufacturerCerts
                onNext={() => goTo(MFR_STEP_BUYER)}
                onBack={() => goTo(MFR_STEP_CATALOG)}
              />
            ) : null}
            {step === MFR_STEP_BUYER ? (
              <StepBuyerRequirements
                onNext={() => goTo(MFR_STEP_REVIEW)}
                onBack={() => goTo(MFR_STEP_CERTIFICATES)}
              />
            ) : null}
            {step === MFR_STEP_REVIEW ? (
              <StepReview
                onBack={() => goTo(MFR_STEP_BUYER)}
                onComplete={(companyId) =>
                  navigate(`/companies/new/done/${companyId}`, { replace: true })
                }
              />
            ) : null}
          </>
        ) : logistics ? (
          <>
            {step === LOG_STEP_DETAILS ? (
              <StepDetails
                onNext={() => goTo(LOG_STEP_SERVICES)}
                onBack={() => goTo(LOG_STEP_TYPE)}
              />
            ) : null}
            {step === LOG_STEP_SERVICES ? (
              <StepLogisticsServices
                onNext={() => goTo(LOG_STEP_GEOGRAPHY)}
                onBack={() => goTo(LOG_STEP_DETAILS)}
              />
            ) : null}
            {step === LOG_STEP_GEOGRAPHY ? (
              <StepLogisticsGeography
                onNext={() => goTo(LOG_STEP_SPECIALIZATION)}
                onBack={() => goTo(LOG_STEP_SERVICES)}
              />
            ) : null}
            {step === LOG_STEP_SPECIALIZATION ? (
              <StepLogisticsSpecialization
                onNext={() => goTo(LOG_STEP_TARIFFS_DOCS)}
                onBack={() => goTo(LOG_STEP_GEOGRAPHY)}
              />
            ) : null}
            {step === LOG_STEP_TARIFFS_DOCS ? (
              <StepLogisticsTariffsDocs
                onNext={() => goTo(LOG_STEP_REVIEW)}
                onBack={() => goTo(LOG_STEP_SPECIALIZATION)}
              />
            ) : null}
            {step === LOG_STEP_REVIEW ? (
              <StepReview
                onBack={() => goTo(LOG_STEP_TARIFFS_DOCS)}
                onComplete={(companyId) =>
                  navigate(`/companies/new/done/${companyId}`, { replace: true })
                }
              />
            ) : null}
          </>
        ) : laboratory ? (
          <>
            {step === LAB_STEP_DETAILS ? (
              <StepDetails
                onNext={() => goTo(LAB_STEP_LICENSES)}
                onBack={() => goTo(LAB_STEP_TYPE)}
              />
            ) : null}
            {step === LAB_STEP_LICENSES ? (
              <StepLabLicenses
                onNext={() => goTo(LAB_STEP_REVIEW)}
                onBack={() => goTo(LAB_STEP_DETAILS)}
              />
            ) : null}
            {step === LAB_STEP_REVIEW ? (
              <StepReview
                onBack={() => goTo(LAB_STEP_LICENSES)}
                onComplete={(companyId) =>
                  navigate(`/companies/new/done/${companyId}`, { replace: true })
                }
              />
            ) : null}
          </>
        ) : (
          <>
            {step === WIZARD_STEP_DETAILS ? (
              <StepDetails
                onNext={() => goTo(WIZARD_STEP_BANK)}
                onBack={() => goTo(WIZARD_STEP_TYPE)}
              />
            ) : null}
            {step === WIZARD_STEP_BANK ? (
              <StepBank
                onNext={() => goTo(WIZARD_STEP_DOCUMENTS)}
                onBack={() => goTo(WIZARD_STEP_DETAILS)}
              />
            ) : null}
            {step === WIZARD_STEP_DOCUMENTS ? (
              <StepDocuments
                onNext={() => goTo(WIZARD_STEP_REVIEW)}
                onBack={() => goTo(WIZARD_STEP_BANK)}
              />
            ) : null}
            {step === WIZARD_STEP_REVIEW ? (
              <StepReview
                onBack={() => goTo(WIZARD_STEP_DOCUMENTS)}
                onComplete={(companyId) =>
                  navigate(`/companies/new/done/${companyId}`, { replace: true })
                }
              />
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}

function clampStep(raw: string | undefined, max: number): number {
  const parsed = Number(raw);
  if (!Number.isInteger(parsed)) return WIZARD_FIRST_STEP;
  return Math.min(Math.max(parsed, WIZARD_FIRST_STEP), max);
}

import { useState } from "react";

import {
  Alert,
  Badge,
  BottomNav,
  Button,
  DateInput,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  Checkbox,
  ChecklistRow,
  ChevronLeftIcon,
  ChipInput,
  ChoiceTile,
  ClockIcon,
  Confetti,
  ConfirmDialog,
  DownloadIcon,
  Dropzone,
  EmptyState,
  FactoryIcon,
  FileRow,
  FlowHeader,
  FormField,
  IconButton,
  IconTile,
  InfoIcon,
  GlobeIcon,
  HashIcon,
  Input,
  MapPinIcon,
  PageHeader,
  PasswordInput,
  ProgressRing,
  Radio,
  RadioCard,
  RegistryIcon,
  Segmented,
  Select,
  Skeleton,
  SpecItem,
  SpecList,
  SpecTile,
  Spinner,
  StatChip,
  StatusStepper,
  StepPanel,
  Stepper,
  StickyActionBar,
  SuccessMark,
  Tabs,
  TaxIcon,
  Textarea,
  Tooltip,
  BoxIcon,
  type BottomNavItem,
  type StatusStep,
  type TabItem,
} from "@/shared/ui";

/**
 * DEV-only gallery of every `shared/ui` primitive — the portal has no unit-test
 * runner, so this page is where the kit is rendered for the P0 e2e spec
 * (`e2e/p0-ui-kit.spec.ts`) and for eyeballing a token change against the
 * mockups in one screen.
 *
 * Mounted only when `import.meta.env.DEV` (see app/router/routes.tsx) — it must
 * never reach a production bundle, and it deliberately needs no auth so the spec
 * can load it without a session.
 */

const WIZARD_STEPS = [
  { id: 1, label: "Тип компании" },
  { id: 2, label: "Данные" },
  { id: 3, label: "Банк" },
  { id: 4, label: "Документы" },
  { id: 5, label: "Проверка" },
] as const;

const ACCOUNT_TYPE_DEMO = [
  {
    id: "buyer",
    title: "Покупатель",
    description: "Закупка сырья и материалов для вашего производства",
    icon: <RegistryIcon size={22} />,
  },
  {
    id: "distributor",
    title: "Дистрибьютор/Трейдер",
    description: "Дистрибуция и торговля промышленным сырьём",
    icon: <FactoryIcon size={22} />,
  },
] as const;

const EIMZO_METHOD_DEMO: readonly TabItem[] = [
  { id: "usb_token", label: "USB Token" },
  { id: "mobile_id", label: "Mobile ID" },
  { id: "cloud_id", label: "Cloud ID" },
];

const TIMELINE: readonly StatusStep[] = [
  { id: "created", label: "Проект создан продавцом", hint: "15.05.2026 10:30", state: "done" },
  { id: "sent", label: "Отправлен покупателю", hint: "15.05.2026 10:32", state: "done" },
  { id: "awaiting", label: "Ожидает подписи покупателя", hint: "Ожидается", state: "current" },
  { id: "signed", label: "Договор подписан обеими сторонами", state: "pending" },
];

/** Minimal glyphs for the nav row — real screens pass their own. */
function NavGlyph({ d }: { d: string }) {
  return (
    <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
      <path d={d} stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

const NAV_ITEMS: readonly BottomNavItem[] = [
  {
    to: "/",
    label: "Главная",
    end: true,
    icon: <NavGlyph d="M3 9l7-6 7 6v8a1 1 0 0 1-1 1h-4v-5H8v5H4a1 1 0 0 1-1-1V9z" />,
  },
  { to: "/requests", label: "Заявки", icon: <NavGlyph d="M5 3h10v14H5zM8 7h4M8 10h4M8 13h3" /> },
  { to: "/market", label: "Маркет", icon: <NavGlyph d="M3 7h14v9H3zM3 7l2-4h10l2 4" /> },
  // Points at this page so exactly one destination is `aria-current` here.
  { to: "/dev/ui", label: "Сделки", badge: 3, icon: <NavGlyph d="M4 6h12v10H4zM7 9h6M7 12h4" /> },
  { to: "/settings", label: "Профиль", icon: <NavGlyph d="M10 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM4 17c0-3 2.7-5 6-5s6 2 6 5" /> },
];

const SECTION_TABS: readonly TabItem[] = [
  { id: "description", label: "Описание" },
  { id: "specs", label: "Характеристики" },
  { id: "documents", label: "Документы", count: 4 },
  { id: "reviews", label: "Отзывы" },
];

const FILTER_TABS: readonly TabItem[] = [
  { id: "all", label: "Все" },
  { id: "pp", label: "PP", count: 12 },
  { id: "hdpe", label: "HDPE", count: 8 },
  { id: "ldpe", label: "LDPE" },
];

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-text-subtle">{title}</h2>
      {children}
    </section>
  );
}

export function UiKitPage() {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [checked, setChecked] = useState(true);
  const [sectionTab, setSectionTab] = useState("description");
  const [accountType, setAccountType] = useState("distributor");
  const [eimzoMethod, setEimzoMethod] = useState("usb_token");
  const [filterTab, setFilterTab] = useState("pp");
  const [availability, setAvailability] = useState("in_stock");
  const [samples, setSamples] = useState("yes");
  const [sampleFee, setSampleFee] = useState("free");
  const [chips, setChips] = useState<string[]>(["MFI: 3.0 г/10мин", "Плотность: 0.90 г/см³"]);

  return (
    // `pb-36` on phones, because this page renders a StickyActionBar — the rule
    // every page using that primitive follows.
    <div className="mx-auto max-w-3xl space-y-8 px-4 py-8 pb-36 md:pb-8">
      <header>
        <h1 className="text-2xl font-semibold text-text">UI kit</h1>
        <p className="mt-1 text-sm text-text-muted">
          Все примитивы дизайн-системы IMEX AI. Страница доступна только в dev-режиме.
        </p>
      </header>

      <Section title="Buttons">
        <div className="flex flex-wrap items-center gap-3">
          <Button data-testid="ui-button-primary">Запросить предложение</Button>
          <Button variant="outline">Связаться с продавцом</Button>
          <Button variant="secondary">Изменить заявку</Button>
          <Button variant="ghost">Отмена</Button>
          <Button variant="danger" data-testid="ui-button-danger">
            Выйти
          </Button>
          <Button variant="gold" data-testid="ui-button-gold">
            Опубликовать заявку
          </Button>
          <Button data-testid="ui-button-disabled" disabled>
            Сохранить изменения
          </Button>
          <Button loading>Загрузка</Button>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Button size="sm">Small</Button>
          <Button size="md">Medium</Button>
          <Button size="lg">Large</Button>
        </div>
      </Section>

      <Section title="Badges">
        <div className="flex flex-wrap items-center gap-2">
          <Badge data-testid="ui-badge-verified" variant="verified">
            Verified Supplier
          </Badge>
          <Badge data-testid="ui-badge-lab" variant="lab-verified">
            Laboratory Verified
          </Badge>
          <Badge data-testid="ui-badge-in-stock" variant="in-stock">
            В наличии
          </Badge>
          <Badge data-testid="ui-badge-on-order" variant="on-order">
            Под заказ
          </Badge>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone="neutral">Черновик</Badge>
          <Badge tone="brand">Активная</Badge>
          <Badge tone="warning">Контракт запрошен</Badge>
          <Badge tone="danger">Отклонено</Badge>
          <Badge tone="info">На модерации</Badge>
          <Badge tone="success">Завершено</Badge>
          <Badge tone="gold">Премиум</Badge>
        </div>
      </Section>

      <Section title="Cards">
        <div className="grid gap-4 sm:grid-cols-2">
          <Card data-testid="ui-card-plain">
            <CardHeader>
              <CardTitle>Обычная карточка</CardTitle>
            </CardHeader>
            <CardBody className="text-sm text-text-muted">border-border</CardBody>
          </Card>
          <Card data-testid="ui-card-accent" variant="accent">
            <CardHeader>
              <CardTitle>Акцентная карточка</CardTitle>
            </CardHeader>
            <CardBody className="text-sm text-text-muted">border-brand-line</CardBody>
          </Card>
        </div>
      </Section>

      <Section title="Metrics">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatChip data-testid="ui-stat-chip" value="50 000+" label="Проверенных компаний" />
          <StatChip value="120+" label="Стран поставок" tone="brand" />
          <StatChip value="98%" label="Довольных клиентов" tone="gold" />
          <StatChip value="1 045" label="PP (гомополимер)" hint="+2,3% USD/MT" />
        </div>
        <div className="flex justify-center py-2">
          <ProgressRing data-testid="ui-progress-ring" value={76} label="AI-проверка компании" />
        </div>
      </Section>

      <Section title="Steppers">
        <Card>
          <CardBody className="space-y-6">
            <Stepper steps={WIZARD_STEPS} current={3} />
            <div data-testid="ui-stepper-stacked">
              <Stepper steps={WIZARD_STEPS} current={3} variant="stacked" />
            </div>
            <div data-testid="ui-status-stepper">
              <StatusStepper steps={TIMELINE} />
            </div>
          </CardBody>
        </Card>
      </Section>

      <Section title="Forms">
        <Card>
          <CardBody className="space-y-4">
            <FormField label="Название компании" required>
              {({ id }) => (
                <Input id={id} data-testid="ui-input" placeholder="OOO GRAND CUP" />
              )}
            </FormField>
            <FormField label="Страна регистрации">
              {({ id }) => (
                <Select
                  id={id}
                  data-testid="ui-select"
                  options={[
                    { value: "UZ", label: "Узбекистан" },
                    { value: "RU", label: "Россия" },
                  ]}
                />
              )}
            </FormField>
            <FormField label="Комментарий" hint="До 300 символов">
              {({ id }) => (
                <Textarea id={id} data-testid="ui-textarea" placeholder="Требуемые характеристики" />
              )}
            </FormField>
            <FormField label="Невалидное поле" error="Введите корректный номер телефона">
              {({ id, invalid }) => <Input id={id} invalid={invalid} defaultValue="+998 12" />}
            </FormField>
            <Checkbox
              id="ui-checkbox"
              label="Принимаю Escrow-расчёты"
              description="Оплата блокируется банком до подтверждения отгрузки"
              checked={checked}
              onChange={(e) => setChecked(e.target.checked)}
            />
            <div className="space-y-2" data-testid="ui-radio">
              {(["free", "paid"] as const).map((fee) => (
                <Radio
                  key={fee}
                  id={`ui-radio-${fee}`}
                  name="ui-radio-group"
                  value={fee}
                  checked={sampleFee === fee}
                  onChange={() => setSampleFee(fee)}
                  label={fee === "free" ? "Бесплатно" : "Платно"}
                />
              ))}
            </div>
            <Segmented
              ariaLabel="Образцы"
              data-testid="ui-segmented"
              value={samples}
              onChange={setSamples}
              options={[
                { value: "yes", label: "Доступны" },
                { value: "no", label: "Не предоставляются" },
              ]}
            />
            <FormField label="Ключевые свойства">
              {({ id }) => (
                <ChipInput
                  id={id}
                  data-testid="ui-chip-input"
                  values={chips}
                  onChange={setChips}
                  placeholder="Например, MFI: 3.0 г/10мин"
                  addLabel="Добавить"
                  removeLabel="Убрать"
                />
              )}
            </FormField>
            <Dropzone
              data-testid="ui-dropzone"
              label="Перетащите файлы или нажмите для загрузки"
              hint="PDF, JPG, PNG (до 10 MB)"
              accept="application/pdf"
              onFiles={() => undefined}
            />
          </CardBody>
        </Card>
      </Section>

      <Section title="Add-product sheets">
        <div className="space-y-4">
          <StepPanel step={3} title="Наличие / Под заказ" counter="Шаг 3 из 7" data-testid="ui-step-panel">
            <div className="grid grid-cols-2 gap-3" data-testid="ui-choice-tiles">
              <ChoiceTile
                name="ui-availability"
                value="in_stock"
                tone="gold"
                checked={availability === "in_stock"}
                onChange={setAvailability}
                icon={<BoxIcon size={22} />}
                title="В наличии"
                description="Товар есть на складе"
              />
              <ChoiceTile
                name="ui-availability"
                value="on_order"
                tone="gold"
                checked={availability === "on_order"}
                onChange={setAvailability}
                icon={<ClockIcon size={22} />}
                title="Под заказ"
                description="Производство по требованию"
              />
            </div>
          </StepPanel>
        </div>
      </Section>

      <Section title="Feedback">
        <div className="space-y-3">
          <Alert tone="info" title="Покупатель получит уведомление">
            И сможет подписать договор онлайн через ЭДО.
          </Alert>
          <Alert tone="success" title="Компания успешно проверена" />
          <Alert tone="warning" title="Требуется лицензия" />
          <Alert tone="danger" title="Публикация невозможна" />
          <div className="flex items-center gap-4">
            <Spinner label="Загрузка" />
            <Tooltip content="Подсказка">
              <span className="text-sm text-text-muted underline decoration-dotted">Наведите</span>
            </Tooltip>
            <Button variant="outline" onClick={() => setConfirmOpen(true)}>
              Открыть диалог
            </Button>
          </div>
          <Skeleton className="h-10 w-full" />
          <EmptyState icon={<BoxIcon size={28} />} title="Предложения не найдены" description="Измените фильтры или зайдите позже." />
        </div>
      </Section>

      <Section title="Page header">
        <Card>
          <CardBody>
            <PageHeader
              title="PP H030 GP"
              subtitle="Полипропилен гомополимер (Injection Molding Grade)"
              badge={<Badge variant="lab-verified">Laboratory Verified</Badge>}
              backTo="/dev/ui"
              backLabel="Назад"
              actions={<Button size="sm">Запросить RFQ</Button>}
            />
          </CardBody>
        </Card>
      </Section>

      <Section title="Tabs">
        <Card>
          <CardBody className="space-y-4">
            <Tabs
              data-testid="ui-tabs-underline"
              items={SECTION_TABS}
              value={sectionTab}
              onChange={setSectionTab}
              label="Разделы товара"
            />
            <Tabs
              data-testid="ui-tabs-pill"
              variant="pill"
              items={FILTER_TABS}
              value={filterTab}
              onChange={setFilterTab}
              label="Категории"
            />
          </CardBody>
        </Card>
      </Section>

      <Section title="Specs">
        <div className="grid gap-3 sm:grid-cols-3">
          <SpecTile icon={<HashIcon />} label="CAS" value="9003-07-0" numeric />
          <SpecTile icon={<HashIcon />} label="HS Code" value="3902.10.9000" numeric />
          <SpecTile icon={<GlobeIcon />} label="Страна" value="Узбекистан" />
        </div>
        <Card>
          <CardHeader icon={<InfoIcon size={16} />} action={<Badge tone="brand">Активен</Badge>}>
            <CardTitle>Данные договора</CardTitle>
          </CardHeader>
          <CardBody>
            <SpecList>
              <SpecItem label="Номер договора" value="IMX-2024-000567" numeric />
              <SpecItem label="Товар" value="PP H030 GP" />
              <SpecItem label="Объём" value="100 MT" numeric />
              <SpecItem label="Цена" value="950 USD/MT" numeric />
              <SpecItem label="Условия поставки" value="CIF Ташкент, Узбекистан" span={2} />
            </SpecList>
          </CardBody>
        </Card>
      </Section>

      <Section title="Documents">
        <div className="space-y-2">
          <FileRow
            name="SDS_PP_H030GP.pdf"
            meta="PDF · 2.4 MB · 12.05.2026"
            status={<Badge tone="success">Принят</Badge>}
            actions={
              <Button size="sm" variant="ghost" aria-label="Скачать">
                <DownloadIcon size={16} />
              </Button>
            }
          />
          <FileRow name="Лицензия_на_экспорт.pdf" meta="PDF · 890 KB" muted />
        </div>
      </Section>

      <Section title="Registration">
        <div className="space-y-6">
          <Card>
            <CardBody>
              <FlowHeader
                title="Регистрация компании"
                leading={
                  <IconButton label="Назад">
                    <ChevronLeftIcon size={20} />
                  </IconButton>
                }
              />
            </CardBody>
          </Card>

          <div className="space-y-3" data-testid="ui-radio-cards">
            {ACCOUNT_TYPE_DEMO.map((option) => (
              <RadioCard
                key={option.id}
                name="ui-kit-account-type"
                value={option.id}
                checked={accountType === option.id}
                onChange={setAccountType}
                title={option.title}
                description={option.description}
                icon={option.icon}
                data-testid={`ui-radio-card-${option.id}`}
              />
            ))}
          </div>

          <Tabs
            variant="segmented"
            items={EIMZO_METHOD_DEMO}
            value={eimzoMethod}
            onChange={setEimzoMethod}
            label="Способ подписи"
            data-testid="ui-tabs-segmented"
          />

          <FormField label="PIN-код от токена" required>
            {({ id }) => (
              <PasswordInput id={id} defaultValue="123456" revealLabel="Показать PIN-код" data-testid="ui-password-input" />
            )}
          </FormField>

          <FormField label="Дата регистрации компании" required>
            {({ id }) => (
              <DateInput id={id} defaultValue="2020-03-12" pickerLabel="Выбрать дату" />
            )}
          </FormField>

          <FormField label="Юридический адрес" required>
            {({ id }) => (
              <Textarea
                id={id}
                rows={2}
                defaultValue="100000, Узбекистан, г. Ташкент, ул. Амира Темура, 123"
                trailing={<MapPinIcon size={18} />}
                data-testid="ui-textarea-adorned"
              />
            )}
          </FormField>

          <Card>
            <CardBody>
              <ul className="divide-y divide-border" data-testid="ui-checklist">
                <ChecklistRow
                  icon={<RegistryIcon size={18} />}
                  title="Проверка в реестре компаний"
                  status="Успешно"
                  state="passed"
                />
                <ChecklistRow
                  icon={<TaxIcon size={18} />}
                  title="Проверка налогового статуса"
                  status="Выполняется"
                  state="running"
                />
                <ChecklistRow
                  icon={<FactoryIcon size={18} />}
                  title="Проверка лицензий"
                  status="Требуется уточнение"
                  state="warning"
                />
              </ul>
            </CardBody>
          </Card>

          <Card>
            <CardBody className="flex flex-col items-center py-8 text-center">
              <SuccessMark data-testid="ui-success-mark" />
              <p className="mt-5 text-base font-semibold text-text">Компания успешно проверена</p>
            </CardBody>
          </Card>

          <Card className="relative overflow-hidden">
            <Confetti />
            <CardBody className="relative flex flex-col items-center py-10 text-center">
              <SuccessMark size="lg" />
              <p className="mt-6 text-2xl font-semibold text-text">Регистрация завершена!</p>
              <SpecList variant="justified" columns={1} className="mt-6 w-full text-start">
                <SpecItem label="ID компании" value="8f1c2b0e-4a77-4d1e-9b0a-1f2c3d4e5f60" />
                <SpecItem label="Дата регистрации" value="12.03.2020" numeric />
                <SpecItem label="Уровень доступа" value="Дистрибьютор" />
              </SpecList>
            </CardBody>
          </Card>

          <div className="flex flex-wrap gap-3" data-testid="ui-icon-tiles">
            <IconTile tone="muted">
              <FactoryIcon size={22} />
            </IconTile>
            <IconTile tone="brand">
              <RegistryIcon size={22} />
            </IconTile>
            <IconTile tone="gold">
              <TaxIcon size={22} />
            </IconTile>
            <IconTile tone="danger">
              <InfoIcon size={22} />
            </IconTile>
          </div>
        </div>
      </Section>

      <Section title="Sticky actions">
        <p className="text-sm text-text-muted">
          На телефоне закрепляется над нижней навигацией; на десктопе — обычная строка.
        </p>
        <StickyActionBar>
          <Button variant="outline" fullWidth>
            Написать продавцу
          </Button>
          <Button fullWidth>Запросить контракт</Button>
        </StickyActionBar>
      </Section>

      <BottomNav items={NAV_ITEMS} />

      <ConfirmDialog
        open={confirmOpen}
        title="Выйти из аккаунта?"
        description="Вы уверены, что хотите выйти?"
        confirmLabel="Выйти"
        cancelLabel="Отмена"
        danger
        onClose={() => setConfirmOpen(false)}
        onConfirm={() => setConfirmOpen(false)}
      />
    </div>
  );
}

import { useState } from "react";

import {
  Alert,
  Badge,
  BottomNav,
  Button,
  Card,
  CardBody,
  CardHeader,
  CardTitle,
  Checkbox,
  ConfirmDialog,
  EmptyState,
  FormField,
  Input,
  ProgressRing,
  Select,
  Skeleton,
  Spinner,
  StatChip,
  StatusStepper,
  Stepper,
  Textarea,
  Tooltip,
  type BottomNavItem,
  type StatusStep,
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
  { id: 3, label: "Проверка" },
  { id: 4, label: "Подпись" },
] as const;

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

  return (
    <div className="mx-auto max-w-3xl space-y-8 px-4 py-8 pb-24 md:pb-8">
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
          </CardBody>
        </Card>
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
          <EmptyState title="Предложения не найдены" description="Измените фильтры или зайдите позже." />
        </div>
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

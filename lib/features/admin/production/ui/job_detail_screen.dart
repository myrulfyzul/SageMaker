import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/network/app_failure.dart';
import '../../../../core/widgets/async_value_view.dart';
import '../../../auth/data/auth_user.dart';
import '../../artisans/state/artisans_provider.dart';
import '../data/production_models.dart';
import '../data/production_validation.dart';
import '../state/production_provider.dart';
import 'production_screen.dart' show OverdueChip;

/// Job detail: status, progress history, and the actions each role may use.
/// Staff assign (Req 24.3, 24.8) and move status (Req 24.4, 24.5); staff and
/// the assigned Artisan_User record progress (Req 24.6, 24.7).
class JobDetailScreen extends ConsumerWidget {
  const JobDetailScreen({super.key, required this.jobId});

  final int jobId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final job = ref.watch(productionJobProvider(jobId));
    final isArtisan = ref.watch(productionRoleProvider) == AppRole.artisan;
    return Scaffold(
      appBar: AppBar(title: Text('Job #$jobId')),
      body: AsyncValueView<ProductionJob>(
        value: job,
        onRetry: () => ref.invalidate(productionJobProvider(jobId)),
        onEmptyAction: () {},
        errorMessage: (e) => e is AppFailure ? e.message : 'Server error',
        data: (j) => ListView(
          padding: const EdgeInsets.all(16),
          children: [
            Text(j.productName, style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 4),
            Text('Status: ${statusLabel(j.status)}'),
            Text('Priority: ${statusLabel(j.priority)} · Quantity: ${j.quantity}'),
            if (j.orderId != null) Text('Order: ${j.orderId}'),
            Text('Artisan: ${j.artisanName ?? 'Not assigned'}'),
            if (j.deadline != null) Text('Deadline: ${j.deadline}'),
            if (j.overdue) const Align(
                alignment: Alignment.centerLeft, child: OverdueChip()),
            if (j.notes.isNotEmpty) Text('Notes: ${j.notes}'),
            const SizedBox(height: 8),
            Semantics(
              label: 'Progress ${j.progressPercent} percent',
              child: LinearProgressIndicator(value: j.progressPercent / 100),
            ),
            Text('${j.progressPercent}% complete'),
            const Divider(height: 32),
            if (!isArtisan) ...[
              if (j.status == 'order_confirmed')
                _AssignForm(job: j)
              else
                _StatusActions(job: j),
              const Divider(height: 32),
            ],
            if (j.artisanId != null) _ProgressForm(job: j),
            if (j.history.isNotEmpty) ...[
              const SizedBox(height: 16),
              Text('Progress history',
                  style: Theme.of(context).textTheme.titleMedium),
              for (final p in j.history.reversed)
                ListTile(
                  dense: true,
                  title: Text('${p.percent}%'),
                  subtitle: Text(
                      [if (p.at != null) p.at!, if (p.note.isNotEmpty) p.note]
                          .join(' · ')),
                ),
            ],
          ],
        ),
      ),
    );
  }
}

String _failureText(Object e) => e is ConflictFailure
    ? _conflictText(e)
    : (e is AppFailure ? e.message : 'Server error');

String _conflictText(ConflictFailure e) {
  for (final d in e.details) {
    if (d is Map && d['current'] != null && d['requested'] != null) {
      return 'Cannot move from ${statusLabel('${d['current']}')} to '
          '${statusLabel('${d['requested']}')}';
    }
  }
  return e.message;
}

class _StatusActions extends ConsumerStatefulWidget {
  const _StatusActions({required this.job});

  final ProductionJob job;

  @override
  ConsumerState<_StatusActions> createState() => _StatusActionsState();
}

class _StatusActionsState extends ConsumerState<_StatusActions> {
  String? _error;
  bool _busy = false;

  Future<void> _move(String status) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await ref
          .read(productionRepositoryProvider)
          .changeStatus(widget.job.id, status);
      ref.invalidate(productionJobProvider(widget.job.id));
      ref.invalidate(productionJobsProvider);
    } on AppFailure catch (e) {
      if (mounted) setState(() => _error = _failureText(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final next = nextStatuses(widget.job.status);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Change status', style: Theme.of(context).textTheme.titleMedium),
        if (next.isEmpty) const Text('No further status changes.'),
        Wrap(
          spacing: 8,
          children: [
            for (final s in next)
              FilledButton.tonal(
                key: ValueKey('move-$s'),
                onPressed: _busy ? null : () => _move(s),
                child: Text('Move to ${statusLabel(s)}'),
              ),
          ],
        ),
        if (_error != null)
          Semantics(
            liveRegion: true,
            child: Text(_error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error)),
          ),
      ],
    );
  }
}

class _AssignForm extends ConsumerStatefulWidget {
  const _AssignForm({required this.job});

  final ProductionJob job;

  @override
  ConsumerState<_AssignForm> createState() => _AssignFormState();
}

class _AssignFormState extends ConsumerState<_AssignForm> {
  final _key = GlobalKey<FormState>();
  late final _qty = TextEditingController(text: '${widget.job.quantity}');
  final _deadline = TextEditingController();
  final _notes = TextEditingController();
  int? _artisan;
  String _priority = 'normal';
  Map<String, String> _server = {};
  String? _error;
  bool _busy = false;

  @override
  void dispose() {
    _qty.dispose();
    _deadline.dispose();
    _notes.dispose();
    super.dispose();
  }

  String? _c(String f, String? local) => local ?? _server[f];

  Future<void> _submit() async {
    setState(() {
      _server = {};
      _error = null;
    });
    if (!_key.currentState!.validate()) return;
    setState(() => _busy = true);
    try {
      await ref.read(productionRepositoryProvider).assign(
            widget.job.id,
            artisanId: _artisan!,
            quantity: int.parse(_qty.text.trim()),
            deadline: _deadline.text.trim(),
            priority: _priority,
            notes: _notes.text,
          );
      ref.invalidate(productionJobProvider(widget.job.id));
      ref.invalidate(productionJobsProvider);
    } on ValidationFailure catch (e) {
      if (!mounted) return;
      setState(() {
        _server = e.fields;
        _error = e.fields.isEmpty ? e.message : null;
      });
      _key.currentState?.validate();
    } on AppFailure catch (e) {
      if (mounted) setState(() => _error = _failureText(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final artisans = ref.watch(artisansProvider).value ?? const [];
    return Form(
      key: _key,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Assign artisan', style: Theme.of(context).textTheme.titleMedium),
          DropdownButtonFormField<int>(
            key: const ValueKey('assign-artisan'),
            initialValue: _artisan,
            isExpanded: true,
            decoration: const InputDecoration(labelText: 'Artisan'),
            items: [
              for (final a in artisans)
                DropdownMenuItem(
                  value: a.id,
                  child: Text(a.availability == 'unavailable'
                      ? '${a.name} (unavailable)'
                      : a.name),
                ),
            ],
            onChanged: (v) => setState(() => _artisan = v),
            validator: (v) =>
                _c('artisanId', v == null ? 'Choose an artisan' : null),
          ),
          TextFormField(
            key: const ValueKey('assign-quantity'),
            controller: _qty,
            keyboardType: TextInputType.number,
            decoration: const InputDecoration(labelText: 'Quantity'),
            validator: (v) => _c('quantity', validateJobQuantity(v)),
          ),
          TextFormField(
            key: const ValueKey('assign-deadline'),
            controller: _deadline,
            keyboardType: TextInputType.datetime,
            decoration:
                const InputDecoration(labelText: 'Deadline (YYYY-MM-DD)'),
            validator: (v) => _c('deadline', validateDeadline(v)),
          ),
          DropdownButtonFormField<String>(
            key: const ValueKey('assign-priority'),
            initialValue: _priority,
            decoration: const InputDecoration(labelText: 'Priority'),
            items: [
              for (final p in productionPriorities)
                DropdownMenuItem(value: p, child: Text(statusLabel(p))),
            ],
            onChanged: (v) => setState(() => _priority = v!),
          ),
          TextFormField(
            key: const ValueKey('assign-notes'),
            controller: _notes,
            maxLength: 1000,
            maxLines: 2,
            decoration: const InputDecoration(labelText: 'Notes'),
            validator: (v) => _c('notes', validateJobNotes(v)),
          ),
          if (_error != null)
            Text(_error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error)),
          FilledButton(
            key: const ValueKey('assign-submit'),
            onPressed: _busy ? null : _submit,
            child: const Text('Assign'),
          ),
        ],
      ),
    );
  }
}

class _ProgressForm extends ConsumerStatefulWidget {
  const _ProgressForm({required this.job});

  final ProductionJob job;

  @override
  ConsumerState<_ProgressForm> createState() => _ProgressFormState();
}

class _ProgressFormState extends ConsumerState<_ProgressForm> {
  final _key = GlobalKey<FormState>();
  late final _percent =
      TextEditingController(text: '${widget.job.progressPercent}');
  final _note = TextEditingController();
  Map<String, String> _server = {};
  String? _error;
  bool _busy = false;

  @override
  void dispose() {
    _percent.dispose();
    _note.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() {
      _server = {};
      _error = null;
    });
    if (!_key.currentState!.validate()) return;
    setState(() => _busy = true);
    try {
      await ref.read(productionRepositoryProvider).addProgress(
          widget.job.id, int.parse(_percent.text.trim()), _note.text);
      _note.clear();
      ref.invalidate(productionJobProvider(widget.job.id));
      ref.invalidate(productionJobsProvider);
    } on ValidationFailure catch (e) {
      if (!mounted) return;
      setState(() {
        _server = e.fields;
        _error = e.fields.isEmpty ? e.message : null;
      });
      _key.currentState?.validate();
    } on AppFailure catch (e) {
      if (mounted) setState(() => _error = _failureText(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Form(
      key: _key,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Update progress',
              style: Theme.of(context).textTheme.titleMedium),
          TextFormField(
            key: const ValueKey('progress-percent'),
            controller: _percent,
            keyboardType: TextInputType.number,
            decoration: const InputDecoration(labelText: 'Progress (0 to 100)'),
            validator: (v) =>
                validateProgressPercent(v) ?? _server['percent'],
          ),
          TextFormField(
            key: const ValueKey('progress-note'),
            controller: _note,
            maxLength: 500,
            decoration: const InputDecoration(labelText: 'Note'),
            validator: (v) => validateProgressNote(v) ?? _server['note'],
          ),
          if (_error != null)
            Text(_error!,
                style: TextStyle(color: Theme.of(context).colorScheme.error)),
          FilledButton(
            key: const ValueKey('progress-submit'),
            onPressed: _busy ? null : _submit,
            child: const Text('Save progress'),
          ),
        ],
      ),
    );
  }
}

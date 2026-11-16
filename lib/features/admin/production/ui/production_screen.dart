import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/network/app_failure.dart';
import '../../../../core/widgets/async_value_view.dart';
import '../../../auth/data/auth_user.dart';
import '../../artisans/state/artisans_provider.dart';
import '../data/production_models.dart';
import '../state/production_provider.dart';
import 'job_detail_screen.dart';

/// Production jobs in a list or board view grouped by status, filterable by
/// status, artisan and priority combined with AND (Req 24.12). An empty
/// result offers to clear the filters (Req 24.13). An Artisan_User sees only
/// their assigned jobs and no artisan filter (Req 6.7, 6.8).
class ProductionScreen extends ConsumerStatefulWidget {
  const ProductionScreen({super.key});

  @override
  ConsumerState<ProductionScreen> createState() => _ProductionScreenState();
}

class _ProductionScreenState extends ConsumerState<ProductionScreen> {
  bool _board = false;

  @override
  Widget build(BuildContext context) {
    final role = ref.watch(productionRoleProvider);
    final isArtisan = role == AppRole.artisan;
    final filters = ref.watch(productionFiltersProvider);
    final jobs = ref.watch(productionJobsProvider);
    void clear() =>
        ref.read(productionFiltersProvider.notifier).set(const ProductionFilters());

    return Scaffold(
      appBar: AppBar(
        title: Text(isArtisan ? 'My jobs' : 'Production'),
        actions: [
          IconButton(
            tooltip: _board ? 'Show list view' : 'Show board view',
            icon: Icon(_board ? Icons.view_list : Icons.view_column),
            onPressed: () => setState(() => _board = !_board),
          ),
          IconButton(
            tooltip: 'Refresh',
            icon: const Icon(Icons.refresh),
            onPressed: () => ref.invalidate(productionJobsProvider),
          ),
        ],
      ),
      body: Column(
        children: [
          _FilterBar(showArtisan: !isArtisan, filters: filters),
          Expanded(
            child: AsyncValueView<List<ProductionJob>>(
              value: jobs,
              onRetry: () => ref.invalidate(productionJobsProvider),
              isEmpty: (items) => items.isEmpty,
              emptyMessage: filters.isEmpty
                  ? (isArtisan
                      ? 'No jobs are assigned to you yet.'
                      : 'No production jobs yet.')
                  : 'No jobs match these filters.',
              emptyActionLabel: filters.isEmpty ? 'Refresh' : 'Clear filters',
              onEmptyAction: filters.isEmpty
                  ? () => ref.invalidate(productionJobsProvider)
                  : clear,
              errorMessage: (e) => e is AppFailure ? e.message : 'Server error',
              data: (items) => _board
                  ? _Board(jobs: items, onOpen: _open)
                  : RefreshIndicator(
                      onRefresh: () async =>
                          ref.invalidate(productionJobsProvider),
                      child: ListView(
                        children: [
                          for (final j in items)
                            _JobTile(job: j, onTap: () => _open(j)),
                        ],
                      ),
                    ),
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _open(ProductionJob j) async {
    await Navigator.of(context).push(
        MaterialPageRoute<void>(builder: (_) => JobDetailScreen(jobId: j.id)));
    ref.invalidate(productionJobsProvider);
  }
}

class _FilterBar extends ConsumerWidget {
  const _FilterBar({required this.showArtisan, required this.filters});

  final bool showArtisan;
  final ProductionFilters filters;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final notifier = ref.read(productionFiltersProvider.notifier);
    final artisans = showArtisan ? ref.watch(artisansProvider).value : null;
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 4),
      child: Row(
        children: [
          _Dropdown<String>(
            keyName: 'filter-status',
            label: 'Status',
            value: filters.status,
            options: {for (final s in productionStatuses) s: statusLabel(s)},
            onChanged: (v) =>
                notifier.set(filters.copyWith(status: () => v)),
          ),
          const SizedBox(width: 8),
          if (showArtisan) ...[
            _Dropdown<int>(
              keyName: 'filter-artisan',
              label: 'Artisan',
              value: filters.artisanId,
              options: {for (final a in artisans ?? const []) a.id: a.name},
              onChanged: (v) =>
                  notifier.set(filters.copyWith(artisanId: () => v)),
            ),
            const SizedBox(width: 8),
          ],
          _Dropdown<String>(
            keyName: 'filter-priority',
            label: 'Priority',
            value: filters.priority,
            options: {for (final p in productionPriorities) p: statusLabel(p)},
            onChanged: (v) =>
                notifier.set(filters.copyWith(priority: () => v)),
          ),
          if (!filters.isEmpty)
            TextButton(
              onPressed: () => notifier.set(const ProductionFilters()),
              child: const Text('Clear filters'),
            ),
        ],
      ),
    );
  }
}

class _Dropdown<T> extends StatelessWidget {
  const _Dropdown({
    required this.keyName,
    required this.label,
    required this.value,
    required this.options,
    required this.onChanged,
  });

  final String keyName;
  final String label;
  final T? value;
  final Map<T, String> options;
  final ValueChanged<T?> onChanged;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 160,
      child: DropdownButtonFormField<T?>(
        key: ValueKey('$keyName-${value ?? 'all'}'),
        initialValue: value,
        isExpanded: true,
        decoration: InputDecoration(labelText: label, isDense: true),
        items: [
          DropdownMenuItem<T?>(value: null, child: Text('All')),
          for (final e in options.entries)
            DropdownMenuItem<T?>(value: e.key, child: Text(e.value)),
        ],
        onChanged: onChanged,
      ),
    );
  }
}

class OverdueChip extends StatelessWidget {
  const OverdueChip({super.key});

  @override
  Widget build(BuildContext context) {
    final c = Theme.of(context).colorScheme;
    return Chip(
      visualDensity: VisualDensity.compact,
      backgroundColor: c.errorContainer,
      avatar: Icon(Icons.schedule, size: 16, color: c.error),
      label: const Text('Overdue'),
    );
  }
}

class _JobTile extends StatelessWidget {
  const _JobTile({required this.job, required this.onTap});

  final ProductionJob job;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      key: ValueKey('job-${job.id}'),
      title: Text('#${job.id} ${job.productName} × ${job.quantity}'),
      subtitle: Text([
        statusLabel(job.status),
        '${job.progressPercent}%',
        statusLabel(job.priority),
        if (job.artisanName != null) job.artisanName!,
        if (job.deadline != null) 'Due ${job.deadline}',
      ].join(' · ')),
      trailing: job.overdue ? const OverdueChip() : null,
      onTap: onTap,
    );
  }
}

class _Board extends StatelessWidget {
  const _Board({required this.jobs, required this.onOpen});

  final List<ProductionJob> jobs;
  final ValueChanged<ProductionJob> onOpen;

  @override
  Widget build(BuildContext context) {
    return ListView(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsets.all(8),
      children: [
        for (final s in productionStatuses)
          SizedBox(
            key: ValueKey('column-$s'),
            width: 240,
            child: Card(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Padding(
                    padding: const EdgeInsets.all(12),
                    child: Text(
                        '${statusLabel(s)} (${jobs.where((j) => j.status == s).length})',
                        style: Theme.of(context).textTheme.titleSmall),
                  ),
                  Expanded(
                    child: ListView(
                      children: [
                        for (final j in jobs.where((j) => j.status == s))
                          _JobTile(job: j, onTap: () => onOpen(j)),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
      ],
    );
  }
}

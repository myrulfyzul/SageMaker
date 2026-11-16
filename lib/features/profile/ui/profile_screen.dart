import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/network/app_failure.dart';
import '../../../core/validators.dart';
import '../../../core/widgets/async_value_view.dart';
import '../../../core/widgets/badge_count.dart';
import '../../../core/widgets/error_view.dart';
import '../../../core/widgets/loading_view.dart';
import '../../auth/state/auth_actions.dart';
import '../../auth/state/session_provider.dart';
import '../../notifications/state/notifications_provider.dart';
import '../state/profile_provider.dart';
import 'address_form_dialog.dart';

/// Profile tab: profile edit, address book, shortcuts and logout
/// (Req 7.1, 7.2, 7.4, 7.6, 7.9, 7.10).
class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionProvider);
    final signedIn = session is SessionSignedIn;
    return Scaffold(
      appBar: AppBar(title: const Text('Profile')),
      body: ListView(
        children: [
          if (signedIn) ...[
            const _ProfileSection(),
            const _AddressSection(),
            const Divider(),
            _link(context, Icons.receipt_long_outlined, 'My orders', '/orders'),
            _link(context, Icons.design_services_outlined, 'Custom orders',
                '/custom-orders'),
            _NotificationsLink(),
          ] else
            ListTile(
              key: const ValueKey('profile-sign-in'),
              leading: const Icon(Icons.login),
              title: const Text('Sign in'),
              subtitle: const Text('Sign in to see your profile and orders'),
              onTap: () => context.push('/login'),
            ),
          _link(context, Icons.info_outline, 'About', '/about'),
          _link(context, Icons.settings_ethernet, 'Connection settings',
              '/settings/connection'),
          if (signedIn)
            ListTile(
              key: const ValueKey('profile-logout'),
              leading: const Icon(Icons.logout),
              title: const Text('Log out'),
              onTap: () => ref.read(authActionsProvider).logout(),
            ),
        ],
      ),
    );
  }

  Widget _link(
          BuildContext context, IconData icon, String label, String path) =>
      ListTile(
        key: ValueKey('profile-link-$path'),
        leading: Icon(icon),
        title: Text(label),
        trailing: const Icon(Icons.chevron_right),
        onTap: () => context.push(path),
      );
}

class _NotificationsLink extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final count = ref.watch(unreadCountProvider).value ?? 0;
    return ListTile(
      key: const ValueKey('profile-link-/notifications'),
      leading: BadgeCount(
          count: count, child: const Icon(Icons.notifications_outlined)),
      title: const Text('Notifications'),
      trailing: const Icon(Icons.chevron_right),
      onTap: () => context.push('/notifications'),
    );
  }
}

class _ProfileSection extends ConsumerWidget {
  const _ProfileSection();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final value = ref.watch(profileProvider);
    if (value.hasError && !value.hasValue) {
      return SizedBox(
        height: 240,
        child: ErrorView(
          message: AsyncValueView.defaultErrorMessage(value.error!),
          onRetry: () => ref.invalidate(profileProvider),
        ),
      );
    }
    if (!value.hasValue) {
      return const SizedBox(height: 120, child: LoadingView());
    }
    final p = value.requireValue;
    return ListTile(
      key: const ValueKey('profile-card'),
      leading: const CircleAvatar(child: Icon(Icons.person)),
      title: Text(p.name),
      subtitle: Text([
        p.email,
        if (p.phone != null && p.phone!.isNotEmpty) p.phone
      ].join('\n')),
      isThreeLine: p.phone != null && p.phone!.isNotEmpty,
      trailing: IconButton(
        key: const ValueKey('profile-edit'),
        tooltip: 'Edit profile',
        icon: const Icon(Icons.edit_outlined),
        onPressed: () async {
          final saved = await showDialog<bool>(
              context: context, builder: (_) => _EditProfileDialog(profile: p));
          if (saved == true) ref.invalidate(profileProvider);
        },
      ),
    );
  }
}

class _EditProfileDialog extends ConsumerStatefulWidget {
  const _EditProfileDialog({required this.profile});
  final Profile profile;

  @override
  ConsumerState<_EditProfileDialog> createState() => _EditProfileState();
}

class _EditProfileState extends ConsumerState<_EditProfileDialog> {
  final _key = GlobalKey<FormState>();
  late final _name = TextEditingController(text: widget.profile.name);
  late final _phone = TextEditingController(text: widget.profile.phone);
  bool _saving = false;
  String? _error;

  @override
  void dispose() {
    _name.dispose();
    _phone.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!_key.currentState!.validate()) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      await ref.read(profileRepositoryProvider).update(_name.text, _phone.text);
      if (mounted) Navigator.of(context).pop(true);
    } on AppFailure catch (e) {
      if (!mounted) return;
      setState(() {
        _saving = false;
        _error = e is ValidationFailure && e.fields.isNotEmpty
            ? e.fields.entries.map((f) => '${f.key}: ${f.value}').join('\n')
            : e.message;
      });
    }
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
        title: const Text('Edit profile'),
        content: Form(
          key: _key,
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            TextFormField(
                key: const ValueKey('profile-name'),
                controller: _name,
                decoration: const InputDecoration(labelText: 'Name'),
                validator: (v) =>
                    (v?.trim().isEmpty ?? true) || v!.trim().length > 100
                        ? 'Name must be 1 to 100 characters'
                        : null),
            TextFormField(
                key: const ValueKey('profile-phone'),
                controller: _phone,
                keyboardType: TextInputType.phone,
                decoration: const InputDecoration(labelText: 'Phone'),
                validator: validateProfilePhone),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(_error!,
                    style:
                        TextStyle(color: Theme.of(context).colorScheme.error)),
              ),
          ]),
        ),
        actions: [
          TextButton(
              onPressed:
                  _saving ? null : () => Navigator.of(context).pop(false),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: _saving ? null : _save, child: const Text('Save')),
        ],
      );
}

class _AddressSection extends ConsumerWidget {
  const _AddressSection();

  Future<void> _run(BuildContext context, WidgetRef ref,
      Future<void> Function() action) async {
    try {
      await action();
      ref.invalidate(addressesProvider);
    } on AppFailure catch (e) {
      if (context.mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(e.message)));
      }
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final value = ref.watch(addressesProvider);
    final repo = ref.read(profileRepositoryProvider);
    final children = <Widget>[
      Padding(
        padding: const EdgeInsets.fromLTRB(16, 16, 8, 0),
        child: Row(children: [
          const Expanded(
              child: Text('Addresses',
                  style: TextStyle(fontWeight: FontWeight.w700, fontSize: 16))),
          TextButton.icon(
            key: const ValueKey('address-add'),
            icon: const Icon(Icons.add),
            label: const Text('Add address'),
            onPressed: () async {
              final saved = await showAddressForm(context);
              if (saved == true) ref.invalidate(addressesProvider);
            },
          ),
        ]),
      ),
    ];
    if (value.hasError && !value.hasValue) {
      children.add(SizedBox(
        height: 240,
        child: ErrorView(
          message: AsyncValueView.defaultErrorMessage(value.error!),
          onRetry: () => ref.invalidate(addressesProvider),
        ),
      ));
    } else if (!value.hasValue) {
      children.add(const SizedBox(height: 80, child: LoadingView()));
    } else if (value.requireValue.isEmpty) {
      children.add(const Padding(
        padding: EdgeInsets.all(16),
        child: Text('You have no saved addresses.'),
      ));
    } else {
      for (final a in value.requireValue) {
        children.add(ListTile(
          key: ValueKey('address-${a.id}'),
          title: Text(a.recipientName + (a.isDefault ? ' (Default)' : '')),
          subtitle: Text([
            a.line1,
            if (a.line2 != null && a.line2!.isNotEmpty) a.line2!,
            '${a.postcode} ${a.city}, ${a.state}',
            a.phone,
          ].join('\n')),
          isThreeLine: true,
          trailing: PopupMenuButton<String>(
            key: ValueKey('address-menu-${a.id}'),
            onSelected: (v) async {
              if (v == 'edit') {
                final saved = await showAddressForm(context, existing: a);
                if (saved == true) ref.invalidate(addressesProvider);
              } else if (v == 'default') {
                await _run(context, ref, () => repo.setDefault(a.id));
              } else if (v == 'delete') {
                await _run(context, ref, () => repo.delete(a.id));
              }
            },
            itemBuilder: (_) => [
              const PopupMenuItem(value: 'edit', child: Text('Edit')),
              if (!a.isDefault)
                const PopupMenuItem(
                    value: 'default', child: Text('Set as default')),
              const PopupMenuItem(value: 'delete', child: Text('Delete')),
            ],
          ),
        ));
      }
    }
    return Column(
        crossAxisAlignment: CrossAxisAlignment.start, children: children);
  }
}

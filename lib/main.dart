import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'app/router.dart';
import 'app/theme.dart';
import 'features/auth/ui/fictional_data_notice.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const ProviderScope(child: SagemakerApp()));
}

class SagemakerApp extends ConsumerWidget {
  const SagemakerApp({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return MaterialApp.router(
      title: 'Sagemaker Asia',
      debugShowCheckedModeBanner: false,
      theme: buildAppTheme(),
      routerConfig: ref.watch(routerProvider),
      builder: (context, child) =>
          FirstLaunchNoticeGate(child: child ?? const SizedBox()),
    );
  }
}

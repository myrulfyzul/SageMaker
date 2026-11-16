import 'package:flutter/material.dart';
import 'about_page.dart';
import 'contact_page.dart';

class MorePage extends StatefulWidget {
  const MorePage({super.key});
  @override
  State<MorePage> createState() => _MorePageState();
}

class _MorePageState extends State<MorePage> {
  bool about = true;
  @override
  Widget build(BuildContext context) => Column(children: [
    Padding(padding: const EdgeInsets.symmetric(vertical: 8),
      child: SegmentedButton<bool>(
        segments: const [ButtonSegment(value: true, label: Text('About')),
          ButtonSegment(value: false, label: Text('Contact'))],
        selected: {about},
        onSelectionChanged: (v) => setState(() => about = v.first),
      )),
    Expanded(child: about ? const AboutPage() : const ContactPage()),
  ]);
}

// ===== Independent demo checkout and tracking (no official shop integration) =====

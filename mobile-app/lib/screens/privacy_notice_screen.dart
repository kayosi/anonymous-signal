import 'package:flutter/material.dart';

/// First screen shown to all users.
/// Explains privacy guarantees clearly before any report submission.
class PrivacyNoticeScreen extends StatefulWidget {
  const PrivacyNoticeScreen({super.key});

  @override
  State<PrivacyNoticeScreen> createState() => _PrivacyNoticeScreenState();
}

class _PrivacyNoticeScreenState extends State<PrivacyNoticeScreen> {
  bool _accepted = false;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: const Color(0xFF0F172A),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const SizedBox(height: 32),

              // Logo / Icon
              Center(
                child: Container(
                  width: 80,
                  height: 80,
                  decoration: BoxDecoration(
                    color: const Color(0xFF1A73E8).withOpacity(0.1),
                    borderRadius: BorderRadius.circular(24),
                    border: Border.all(
                      color: const Color(0xFF1A73E8).withOpacity(0.3),
                    ),
                  ),
                  child: const Icon(
                    Icons.shield_outlined,
                    color: Color(0xFF1A73E8),
                    size: 40,
                  ),
                ),
              ),

              const SizedBox(height: 24),

              // Title
              const Center(
                child: Text(
                  'Anonymous Signal',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 26,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),

              const SizedBox(height: 8),

              Center(
                child: Text(
                  'Report safely. Remain anonymous.',
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.6),
                    fontSize: 14,
                  ),
                ),
              ),

              const SizedBox(height: 40),

              // Privacy guarantees
              Expanded(
                child: SingleChildScrollView(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'Our Privacy Promise',
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: 18,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const SizedBox(height: 16),

                      _PrivacyItem(
                        icon: Icons.location_off,
                        title: 'No Location Tracking',
                        description:
                            'We never collect your GPS coordinates. You may optionally share a general area name.',
                      ),
                      _PrivacyItem(
                        icon: Icons.person_off,
                        title: 'No Identity Required',
                        description:
                            'No account. No phone number. No email. Reports are completely anonymous.',
                      ),
                      _PrivacyItem(
                        icon: Icons.phonelink_erase,
                        title: 'No Device Tracking',
                        description:
                            'Your IP address, device fingerprint, and browser details are never stored.',
                      ),
                      _PrivacyItem(
                        icon: Icons.lock,
                        title: 'End-to-End Encryption',
                        description:
                            'All reports are encrypted before storage using AES-256 encryption.',
                      ),
                      _PrivacyItem(
                        icon: Icons.delete_sweep,
                        title: 'Metadata Stripped',
                        description:
                            'EXIF data (camera model, GPS in photos) and audio metadata are removed automatically.',
                      ),

                      const SizedBox(height: 24),

                      // Purpose statement
                      Container(
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          color: const Color(0xFF1A73E8).withOpacity(0.1),
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(
                            color: const Color(0xFF1A73E8).withOpacity(0.2),
                          ),
                        ),
                        child: const Text(
                          '📋 Reports are used exclusively for public safety intelligence. '
                          'They help authorities identify patterns, prioritize responses, '
                          'and protect communities.',
                          style: TextStyle(
                            color: Colors.white70,
                            fontSize: 13,
                            height: 1.5,
                          ),
                        ),
                      ),

                      const SizedBox(height: 24),

                      // Accept checkbox
                      Row(
                        children: [
                          Checkbox(
                            value: _accepted,
                            onChanged: (val) =>
                                setState(() => _accepted = val ?? false),
                            activeColor: const Color(0xFF1A73E8),
                          ),
                          const Expanded(
                            child: Text(
                              'I understand and accept the privacy terms',
                              style: TextStyle(color: Colors.white70, fontSize: 14),
                            ),
                          ),
                        ],
                      ),

                      const SizedBox(height: 16),

                      // Continue button
                      SizedBox(
                        width: double.infinity,
                        height: 54,
                        child: ElevatedButton(
                          onPressed: _accepted
                              ? () => Navigator.pushReplacementNamed(context, '/home')
                              : null,
                          style: ElevatedButton.styleFrom(
                            backgroundColor: const Color(0xFF1A73E8),
                            foregroundColor: Colors.white,
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(14),
                            ),
                            disabledBackgroundColor:
                                const Color(0xFF1A73E8).withOpacity(0.3),
                          ),
                          child: const Text(
                            'Continue',
                            style: TextStyle(
                              fontSize: 16,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                      ),

                      const SizedBox(height: 24),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _PrivacyItem extends StatelessWidget {
  final IconData icon;
  final String title;
  final String description;

  const _PrivacyItem({
    required this.icon,
    required this.title,
    required this.description,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: Colors.green.withOpacity(0.15),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Icon(icon, color: Colors.greenAccent, size: 20),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.w600,
                    fontSize: 14,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  description,
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.6),
                    fontSize: 12,
                    height: 1.4,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

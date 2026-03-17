#!/usr/bin/env node
/**
 * SteadiDay — Submit sitemap to Google Search Console
 * 
 * Uses a Google Cloud Service Account to authenticate and submit
 * the sitemap via the Search Console API.
 * 
 * Requires:
 *   - npm install googleapis google-auth-library
 *   - GOOGLE_SEARCH_CONSOLE_JSON_KEY env var (base64-encoded service account JSON)
 */

const { google } = require('googleapis');
const { JWT } = require('google-auth-library');

const SITE_URL = 'https://www.steadiday.com/';
const SITEMAP_URL = 'https://www.steadiday.com/sitemap.xml';

async function main() {
    console.log('🔍 Submitting sitemap to Google Search Console...');
    console.log(`   Site: ${SITE_URL}`);
    console.log(`   Sitemap: ${SITEMAP_URL}`);

    // Decode the base64-encoded service account key from env
    const keyBase64 = process.env.GOOGLE_SEARCH_CONSOLE_JSON_KEY;
    if (!keyBase64) {
        console.error('❌ GOOGLE_SEARCH_CONSOLE_JSON_KEY environment variable not set.');
        console.error('   Skipping Google Search Console submission.');
        process.exit(0); // Exit gracefully so the workflow continues
    }

    let keys;
    try {
        keys = JSON.parse(Buffer.from(keyBase64, 'base64').toString('utf-8'));
    } catch (e) {
        console.error('❌ Failed to parse service account JSON key:', e.message);
        process.exit(1);
    }

    // Create authenticated client
    const client = new JWT({
        email: keys.client_email,
        key: keys.private_key,
        scopes: [
            'https://www.googleapis.com/auth/webmasters',
            'https://www.googleapis.com/auth/webmasters.readonly',
        ],
    });

    google.options({ auth: client });
    const searchconsole = google.searchconsole('v1');

    try {
        // Submit the sitemap
        await searchconsole.sitemaps.submit({
            feedpath: SITEMAP_URL,
            siteUrl: SITE_URL,
        });
        console.log('✅ Sitemap submitted successfully to Google Search Console!');
    } catch (e) {
        console.error('❌ Error submitting sitemap:', e.message);
        if (e.response) {
            console.error('   Status:', e.response.status);
            console.error('   Data:', JSON.stringify(e.response.data, null, 2));
        }
        // Don't fail the workflow — log and continue
        process.exit(0);
    }

    // Optionally, list current sitemaps to confirm
    try {
        const res = await searchconsole.sitemaps.list({
            siteUrl: SITE_URL,
        });
        if (res.data.sitemap) {
            console.log('\n📋 Current sitemaps in Search Console:');
            for (const sm of res.data.sitemap) {
                console.log(`   ${sm.path} — ${sm.lastSubmitted} (${sm.isPending ? 'pending' : 'processed'})`);
            }
        }
    } catch (e) {
        // Non-critical, just skip
        console.log('   (Could not list sitemaps:', e.message, ')');
    }
}

main();

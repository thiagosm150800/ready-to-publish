async def run_test(page, output_dir, page_url):
    import re

    async def run():
        try:
            await page.set_viewport_size({"width": 375, "height": 667})
            await page.wait_for_selector('[data-testid="login-screen"]', timeout=15000)
            print('PASS: login screen loaded')
            cpf = '153.509.460-56'
            field = page.locator('[data-testid="auth-cpf-input"]')
            await field.fill(cpf)
            await page.locator('[data-testid="auth-submit-button"]').click(force=True)
            await page.wait_for_timeout(1200)
            title = await page.locator('[data-testid="auth-notice-title"]').text_content()
            print(f'NOTICE: {title}')
            assert title == 'Aguardando liberação', f'Unexpected notice: {title}'
            print('PASS: new CPF shows pending notice')
            await page.locator('[data-testid="open-admin-button"]').click(force=True)
            await page.wait_for_selector('[data-testid="admin-login-screen"]', timeout=5000)
            await page.locator('[data-testid="admin-password-input"]').fill('Rapido-570c2c10')
            await page.locator('[data-testid="admin-login-button"]').click(force=True)
            await page.wait_for_selector('[data-testid="admin-screen"]', timeout=10000)
            print('PASS: admin login and pending list loaded')
            cards = page.locator('[data-testid^="admin-user-"]')
            # locate exact card by CPF text
            card = page.locator('[data-testid^="admin-user-"]').filter(has_text='153.509.460-56').first
            await card.wait_for(timeout=5000)
            card_id = await card.get_attribute('data-testid')
            uid = card_id.replace('admin-user-','')
            await page.locator(f'[data-testid="admin-grant-7-{uid}"]').click(force=True)
            await page.wait_for_timeout(1200)
            await page.locator('[data-testid="admin-filter-approved"]').click(force=True)
            await page.wait_for_timeout(700)
            await page.locator('[data-testid="admin-filter-pending"]').click(force=True)
            await page.wait_for_timeout(700)
            print('PASS: admin approval action completed')
            await page.goto('https://ready-to-publish-10--0flvuhva.preview.emergentagent.com/login')
            await page.wait_for_selector('[data-testid="login-screen"]', timeout=10000)
            await page.locator('[data-testid="auth-cpf-input"]').fill(cpf)
            await page.locator('[data-testid="auth-submit-button"]').click(force=True)
            await page.wait_for_selector('[data-testid="painel-screen"]', timeout=12000)
            await page.wait_for_selector('[data-testid="app-card-rapido"]', timeout=5000)
            await page.wait_for_selector('[data-testid="app-card-moove"]', timeout=5000)
            status = await page.locator('[data-testid="service-status-text"]').text_content()
            print(f'SERVICE STATUS: {status}')
            assert status == 'Modo prévia'
            print('PASS: approved driver reaches panel with both app cards and preview mode')
            await page.locator('[data-testid="open-account-button"]').click(force=True)
            await page.wait_for_selector('[data-testid="account-screen"]', timeout=5000)
            print('PASS: account navigation loaded')
        except AssertionError as e:
            print(f'FINDING: {e}')
        except Exception as e:
            print(f'FINDING: UI flow failed: {e}')

    await run()

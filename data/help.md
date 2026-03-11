=== en ===

# How to Connect Your Android Device

## Quick Start

**First time here? Pick your scenario:**

:::nav
🔌 Never connected before → USB Connection
📱 Android 11+ with Wireless Debugging → Wi-Fi Connection (Android 11+)
📡 Android 10 or older → Wi-Fi Connection (Android 10 and Below)
:::

---

**Already set up? Here's the short version:**

For Android 11+:
1. Enable Wireless Debugging (Settings → Developer options)
2. Keep screen unlocked
3. Launch scrcpy UI — device appears automatically in 3–5 seconds
4. Click Connect

For Android 10 and below:
1. Connect USB + run `adb tcpip 5555`
2. Disconnect USB
3. Enter YOUR_IP:5555 in the Wi-Fi field
4. Click Connect

---

## USB Connection

> Recommended for first-time setup

**Step 1: Enable Developer Options**
- Open Settings on your Android device
- Navigate to About phone (or About device)
- Find Build number and tap it 7 times
- You'll see a message: "You are now a developer!"

**Step 2: Enable USB Debugging**
- Go to Settings → System → Developer options
- Find and enable USB debugging
- Connect your phone to PC using USB cable
- On your phone, accept the "Allow USB debugging" prompt
- Check "Always allow from this computer" for convenience

**Step 3: Verify Connection**
- Your device should now appear in the dropdown list
- Click Connect button to start mirroring

> Tip: Use a good quality USB cable. Some cheap cables only support charging, not data transfer!

---

## Wi-Fi Connection (Android 11+)

> No cables, no manual IP entry — the app finds your device automatically via Wireless Debugging

**Step 1: First-time USB setup (one time only)**
- Complete all steps from the USB Connection section above
- This pairs your PC with the phone — you won't need to do it again

**Step 2: Enable Wireless Debugging**
- Go to Settings → System → Developer options
- Find and enable Wireless debugging

**Step 3: Connect**
- Disconnect USB cable
- Unlock your phone screen
- Launch scrcpy UI — your device will appear automatically in 3–5 seconds
- Click Connect

> Important: Phone screen must be unlocked. Wireless Debugging pauses when the screen is off.

> Your phone and PC must be on the same Wi-Fi network!

---

## Wi-Fi Connection (Android 10 and Below)

> For devices without the Wireless Debugging menu. Requires manual IP entry.

**Step 1: Connect via USB**
- Complete the USB Connection steps first
- Keep the USB cable connected

**Step 2: Enable TCP/IP Mode**
- Open Command Prompt or PowerShell on your PC
- Run: `adb tcpip 5555`
- Wait for confirmation message

**Step 3: Find Your Phone's IP Address**
- On your phone: Settings → About phone → Status (or Network info)
- Find the IP address entry (example: `192.168.1.10`)

**Step 4: Connect Wirelessly**
- Disconnect the USB cable
- In scrcpy UI, enter YOUR_IP:5555 in the Wi-Fi field
- Click Connect

> Note: If your phone's IP changes (after reconnecting to Wi-Fi), you'll need to enter the new IP. To avoid this — assign a static IP to your phone in your router settings.

---

## Troubleshooting

**Device not showing up?**
- Try a different USB cable — many cables are charge-only!
- Install manufacturer's USB drivers (Samsung, Xiaomi, etc.)
- Restart ADB server:
  ```bash
  adb kill-server
  adb start-server
  ```
- Check USB connection mode — should be "File Transfer" or "MTP", not "Charging only"

**"Unauthorized" error?**
- Accept the USB debugging prompt on your phone screen
- If it doesn't appear: Developer options → Revoke USB debugging authorizations → reconnect USB → accept prompt again

**Wi-Fi connection keeps dropping?**
- Phone and PC must be on the same Wi-Fi network
- Disable battery optimization for Wireless Debugging:
  Settings → Apps → Special access → Battery optimization → find "Wireless debugging" → Don't optimize
- Some routers block device-to-device communication — look for "AP Isolation" or "Client Isolation" and disable it
- 5GHz Wi-Fi is faster and more stable than 2.4GHz

**Still having issues?**
- Temporarily disable firewall to test
- Verify USB connection works before trying Wi-Fi

---

## Keyboard Input for Multiple Languages

Want to type in Ukrainian, Spanish, or other languages?

1. In Keyboard & Clipboard → Keyboard Input, select "UHID (multilingual)"
2. Connect to your device
3. Press Alt+K in the scrcpy window — Android keyboard settings will open
4. Select "scrcpy" under "Physical keyboard"
5. Use Ctrl+Space to switch between languages on Android

> Note: UHID mode requires Android 13+ for best compatibility

> Alt+Shift switches language on PC keyboard only

---

Need more help? Check the scrcpy documentation:
https://github.com/Genymobile/scrcpy


=== ua ===

# Як підключити Android пристрій

## Швидкий старт

**Вперше тут? Обери свій варіант:**

:::nav
🔌 Ще ніколи не підключав → Підключення через USB
📱 Android 11+ з Бездротовим налагодженням → Підключення через Wi-Fi (Android 11+)
📡 Android 10 або старіший → Підключення через Wi-Fi (Android 10 і нижче)
:::

---

**Вже налаштовано? Коротка версія:**

Для Android 11+:
1. Увімкни Бездротове налагодження (Налаштування → Для розробників)
2. Тримай екран розблокованим
3. Запусти scrcpy UI — пристрій з'явиться автоматично за 3–5 секунд
4. Натисни Підключити

Для Android 10 і нижче:
1. Підключи USB + виконай `adb tcpip 5555`
2. Від'єднай USB
3. Введи ВАШ_IP:5555 у поле Wi-Fi
4. Натисни Підключити

---

## Підключення через USB

> Рекомендовано для першого налаштування

**Крок 1: Увімкнути параметри розробника**
- Відкрий Налаштування на Android пристрої
- Перейди до Про телефон (або Про пристрій)
- Знайди Номер збірки і натисни 7 разів
- Побачиш повідомлення: "Тепер ви розробник!"

**Крок 2: Увімкнути налагодження USB**
- Перейди до Налаштування → Система → Для розробників
- Знайди і увімкни Налагодження USB
- Підключи телефон до ПК кабелем USB
- На телефоні прийми запит "Дозволити налагодження USB"
- Постав галочку "Завжди дозволяти з цього комп'ютера"

**Крок 3: Перевірити підключення**
- Пристрій з'явиться у випадному списку
- Натисни кнопку Підключити для початку трансляції

> Порада: Використовуй якісний USB кабель. Деякі дешеві кабелі підтримують тільки зарядку!

---

## Підключення через Wi-Fi (Android 11+)

> Без кабелів і ручного введення IP — програма знаходить пристрій автоматично через Бездротове налагодження

**Крок 1: Одноразове налаштування через USB**
- Виконай всі кроки з розділу Підключення через USB
- Це створює пару між ПК і телефоном — більше робити не потрібно

**Крок 2: Увімкнути Бездротове налагодження**
- Перейди до Налаштування → Система → Для розробників
- Знайди і увімкни Бездротове налагодження

**Крок 3: Підключитись**
- Від'єднай USB кабель
- Розблокуй екран телефону
- Запусти scrcpy UI — пристрій з'явиться автоматично за 3–5 секунд
- Натисни Підключити

> Важливо: Екран телефону має бути розблокованим. Бездротове налагодження призупиняється коли екран вимкнений.

> Телефон і ПК мають бути підключені до однієї Wi-Fi мережі!

---

## Підключення через Wi-Fi (Android 10 і нижче)

> Для пристроїв без меню Бездротового налагодження. Потребує ручного введення IP.

**Крок 1: Підключитись через USB**
- Спочатку виконай кроки підключення через USB
- Залиш USB кабель підключеним

**Крок 2: Увімкнути режим TCP/IP**
- Відкрий Командний рядок або PowerShell на ПК
- Виконай: `adb tcpip 5555`
- Дочекайся повідомлення про підтвердження

**Крок 3: Знайти IP-адресу телефону**
- На телефоні: Налаштування → Про телефон → Статус (або Відомості про мережу)
- Знайди пункт IP-адреса (наприклад: `192.168.1.10`)

**Крок 4: Підключитись бездротово**
- Від'єднай USB кабель
- У scrcpy UI введи ВАШ_IP:5555 у поле Wi-Fi
- Натисни Підключити

> Примітка: Якщо IP телефону зміниться (після повторного підключення до Wi-Fi) — потрібно ввести новий IP. Щоб уникнути цього — призначте статичний IP телефону в налаштуваннях роутера.

---

## Вирішення проблем

**Пристрій не відображається?**
- Спробуй інший USB кабель — багато кабелів підтримують тільки зарядку!
- Встанови USB драйвери виробника (Samsung, Xiaomi тощо)
- Перезапусти ADB сервер:
  ```bash
  adb kill-server
  adb start-server
  ```
- Перевір режим USB підключення — має бути "Передача файлів" або "MTP", не "Тільки зарядка"

**Помилка "Unauthorized"?**
- Прийми запит налагодження USB на екрані телефону
- Якщо запит не з'являється: Для розробників → Відкликати дозволи налагодження USB → від'єднай і підключи USB → прийми запит знову

**Wi-Fi підключення постійно розривається?**
- Телефон і ПК мають бути в одній Wi-Fi мережі
- Вимкни оптимізацію батареї для Бездротового налагодження:
  Налаштування → Додатки → Спеціальний доступ → Оптимізація батареї → знайди "Бездротове налагодження" → Не оптимізувати
- Деякі роутери блокують зв'язок між пристроями — шукай "AP Isolation" або "Client Isolation" і вимкни
- 5GHz Wi-Fi швидше і стабільніше ніж 2.4GHz

**Все ще є проблеми?**
- Тимчасово вимкни файрвол для тестування
- Перевір що USB підключення працює перед спробою Wi-Fi

---

## Введення клавіатурою багатьма мовами

Хочеш друкувати українською, польською або іншими мовами?

1. У розділі "Клавіатура та буфер обміну" → "Ввід з клавіатури" обери "UHID (багатомовний)"
2. Підключись до пристрою
3. Натисни Alt+K у вікні scrcpy — відкриються налаштування клавіатури Android
4. Обери "scrcpy" у пункті "Фізична клавіатура"
5. Використовуй Ctrl+Space для перемикання між мовами на Android

> Примітка: Режим UHID потребує Android 13+ для найкращої сумісності

> Alt+Shift перемикає мову лише на клавіатурі ПК

---

Потрібна додаткова допомога? Документація scrcpy:
https://github.com/Genymobile/scrcpy

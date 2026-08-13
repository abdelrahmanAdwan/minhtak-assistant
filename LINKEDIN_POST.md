# LinkedIn post — ready to publish

> Attach the four screenshots from `screenshots/` (or a short screen recording of the live
> app). Both language versions below say the same thing; pick one.

---

## English version

🎓 I shipped the capstone of my AI training programme: a production-deployed Arabic AI assistant that chats, calls real tools, reads your CV, and remembers the conversation.

**▶ Live: https://minhtak-assistant.fly.dev**

**The problem**
Arab students hunting fully-funded Master's scholarships juggle three separate things: stale listing sites, their own CV, and a calculator for whether the stipend actually covers rent. And the assistants that claim to help will happily invent a deadline that does not exist — which, for a student who plans a year around it, is worse than no answer at all.

**What I built**
One assistant over a live, human-verified scholarship catalogue. It can search the real catalogue, read a PDF you upload, check the weather in a study destination, and do grounded budget math — deciding for itself which of those a given question needs.

**The architectural decision I'm most pleased with**
The obvious way to combine a chatbot, a tool-calling agent and a RAG pipeline is three modes behind three buttons. I rejected that, because it pushes the routing decision onto the user: *"is this a catalogue question or a document question?"* — something they often can't answer.

Instead, **retrieval over your uploaded PDF is registered as just another tool**, beside the catalogue search and the calculator. The model routes. Three things fall out for free:

🔹 One conversation history — so *"which of those two scholarships fits my CV better?"* is answerable at all. Separate modes simply cannot answer it.
🔹 One set of grounding rules, in one place, instead of re-stated per mode.
🔹 Chaining with no orchestration code: search the catalogue → read the CV → compute the funding gap.

**Key features**
✅ Arabic-first RTL chat, light and dark, responsive to 390px, no framework and no build step
✅ 5 tools via Gemini function calling in AUTO mode
✅ PDF → chunk → embed → cosine retrieval, per session and fully in-memory
✅ Conversation history split between server (model memory) and browser (your transcript)
✅ A visible **trace chip under every reply** showing which tools ran and what they returned
✅ Typed errors end to end — no stack trace ever reaches the chat window

**Challenges, and what I did about them**

1️⃣ **Fly.io deployed two machines and quietly broke my sessions.** Its default HA pair round-robins requests, and my sessions live in process memory — so users would randomly "lose" the CV they had just uploaded. Fixed with one machine, one worker, and the ceiling documented in the README instead of hidden: scaling out needs a shared session store, and I named exactly which two files would change.

2️⃣ **An empty red error bar rendered on first paint.** The cause was CSS, not logic: `.banner { display: flex }` overrides the HTML `hidden` attribute, because an author rule beats the browser's `[hidden] { display: none }`. One line — `[hidden] { display: none !important; }` — fixed that and the same latent bug in the document bar.

3️⃣ **My own screenshot script lied to me.** It waited for a new assistant bubble before capturing — but the *typing indicator* is an assistant bubble, so every screenshot caught a half-finished answer. A good reminder that your test harness needs the same scrutiny as your app.

**Biggest lesson**
Grounding is an architecture problem, not a prompt problem. Telling a model "don't hallucinate" is a wish. Giving it tools as the only route to facts, refusing to advertise a tool the session can't serve, and failing loudly when the loop runs out of steps — that's a design that can't hallucinate a deadline, because it never had one to invent.

**Tech:** Python · FastAPI · Google Gemini (function calling + embeddings) · pypdf · NumPy · Docker · Fly.io · vanilla JS/CSS

🔗 GitHub: https://github.com/abdelrahmanAdwan/minhtak-assistant
▶ Live: https://minhtak-assistant.fly.dev
🌍 The platform behind it: https://minhtak.com

#AI #LLM #RAG #AIAgents #Python #FastAPI #Gemini #SoftwareEngineering

---

## النسخة العربية

🎓 أطلقت المشروع الختامي لبرنامج تدريبي في الذكاء الاصطناعي: مساعد عربي منشور فعليًا يحاور، ويستدعي أدوات حقيقية، ويقرأ سيرتك الذاتية، ويتذكّر المحادثة.

**▶ التطبيق الحي: https://minhtak-assistant.fly.dev**

**المشكلة**
الطالب العربي الباحث عن منحة ماجستير ممولة بالكامل يوازن بين ثلاثة أشياء منفصلة: مواقع إعلانات بيانات قديمة، وسيرته الذاتية، وآلة حاسبة ليعرف هل الراتب يغطي الإيجار. والمساعدات التي تدّعي مساعدته تخترع له موعدًا نهائيًا غير موجود — وهذا لطالب يرتّب سنته كاملة على ذلك الموعد أسوأ من لا إجابة.

**ما بنيته**
مساعد واحد فوق كتالوج منح حي ومُوثَّق بشريًا: يبحث في الكتالوج الحقيقي، ويقرأ ملف PDF ترفعه، ويستعلم عن طقس مدينة الدراسة، ويحسب ميزانيتك — ويقرر بنفسه أي هذه يحتاجه كل سؤال.

**القرار المعماري الذي أعتز به**
الطريقة البديهية لدمج شات بوت ووكيل أدوات ومسار RAG هي ثلاثة أوضاع خلف ثلاثة أزرار. رفضتُها لأنها تحمّل المستخدم قرار التوجيه: «هل سؤالي عن الكتالوج أم عن ملفي؟» — وهو غالبًا لا يعرف.

بدلًا من ذلك، **جعلت الاسترجاع من ملفك أداة كسائر الأدوات**، إلى جانب البحث في الكتالوج والحاسبة. النموذج هو من يوجّه. وينتج عن ذلك مجانًا:

🔹 سجل محادثة واحد — فيصبح سؤال «أي المنحتين تناسب سيرتي أكثر؟» قابلًا للإجابة أصلًا؛ الأوضاع المنفصلة لا تستطيع.
🔹 قواعد استناد واحدة في مكان واحد بدل تكرارها لكل وضع.
🔹 تسلسل الأدوات بلا كود تنسيق: ابحث في الكتالوج ← اقرأ السيرة ← احسب فجوة التمويل.

**أبرز المزايا**
✅ محادثة عربية RTL، فاتح وداكن، متجاوبة حتى 390 بكسل، بلا إطار عمل وبلا خطوة بناء
✅ 5 أدوات عبر function calling من Gemini بوضع AUTO
✅ PDF ← تقطيع ← تضمين ← استرجاع بالتشابه، لكل جلسة وفي الذاكرة بالكامل
✅ سجل محادثات مقسوم بين الخادم (ذاكرة النموذج) والمتصفّح (نصّك أنت)
✅ **شارة أدوات ظاهرة تحت كل رد** تبيّن ما استُدعي وما أرجعه
✅ أخطاء مصنّفة من الطرف إلى الطرف — لا يصل أي stack trace إلى نافذة المحادثة

**تحديات وكيف عالجتها**

1️⃣ **Fly.io نشر جهازين فكسر جلساتي بصمت.** الوضع الافتراضي زوج جهازين يوزّع الطلبات بالتناوب، وجلساتي في ذاكرة العملية — فيفقد المستخدم عشوائيًا الملف الذي رفعه للتو. الحل: جهاز واحد وعامل واحد، مع توثيق السقف في الـ README بدل إخفائه: التوسع الأفقي يحتاج مخزن جلسات مشترك، وسمّيت الملفين اللذين سيتغيّران بالضبط.

2️⃣ **شريط خطأ أحمر فارغ يظهر عند أول رسم.** السبب CSS لا منطق: قاعدة `.banner { display: flex }` تتغلب على خاصية `hidden` لأن قاعدة المؤلف تسبق قاعدة المتصفح. سطر واحد `[hidden] { display: none !important; }` أصلحها وأصلح العطل الكامن نفسه في شريط الملفات.

3️⃣ **سكربت لقطات الشاشة عندي كذب عليّ.** كان ينتظر ظهور فقاعة رد جديدة قبل التصوير — لكن مؤشّر الكتابة نفسه فقاعة رد، فكانت كل لقطة تلتقط إجابة نصف مكتملة. تذكير جيد بأن أدوات الاختبار تستحق التدقيق نفسه الذي يستحقه التطبيق.

**أكبر درس**
الاستناد مسألة معمارية لا مسألة صياغة. أن تقول للنموذج «لا تهلوس» أمنية. أما أن تجعل الأدوات طريقه الوحيد إلى الحقائق، وألا تعلن عن أداة لا تستطيع الجلسة خدمتها، وأن تفشل بصوت عالٍ حين تنفد خطوات الحلقة — فهذا تصميم لا يستطيع اختراع موعد نهائي، لأنه لم يملك يومًا ما يخترعه منه.

**التقنيات:** Python · FastAPI · Google Gemini · pypdf · NumPy · Docker · Fly.io · JS/CSS خام

🔗 GitHub: https://github.com/abdelrahmanAdwan/minhtak-assistant
▶ التطبيق: https://minhtak-assistant.fly.dev
🌍 المنصة: https://minhtak.com

#الذكاء_الاصطناعي #AI #RAG #Python #FastAPI #Gemini

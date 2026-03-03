import { Hono } from "npm:hono";
import { cors } from "npm:hono/cors";
import { logger } from "npm:hono/logger";
import { createClient } from "npm:@supabase/supabase-js@2";
import * as kv from "./kv_store.tsx";

const app = new Hono();

const supabase = createClient(
  Deno.env.get('SUPABASE_URL') ?? '',
  Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? '',
);

// Enable logger
app.use('*', logger(console.log));

// Enable CORS for all routes and methods
app.use(
  "/*",
  cors({
    origin: "*",
    allowHeaders: ["Content-Type", "Authorization"],
    allowMethods: ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    exposeHeaders: ["Content-Length"],
    maxAge: 600,
  }),
);

// Health check endpoint
app.get("/make-server-0ad4a249/health", (c) => {
  return c.json({ status: "ok" });
});

// Sign up endpoint
app.post("/make-server-0ad4a249/signup", async (c) => {
  try {
    const body = await c.req.json();
    const { email, password, name, telegramId } = body;

    // Create user with Supabase Auth
    const { data, error } = await supabase.auth.admin.createUser({
      email,
      password,
      user_metadata: { name, telegramId },
      // Automatically confirm the user's email since an email server hasn't been configured.
      email_confirm: true
    });

    if (error) {
      console.error('Signup error:', error);
      return c.json({ error: error.message }, 400);
    }

    // Initialize user data in KV store
    const userId = data.user.id;
    await kv.set(`user:${userId}`, {
      id: userId,
      name,
      email,
      telegramId,
      balance: 0,
      referralCode: `REF${userId.slice(0, 8).toUpperCase()}`,
      referralsCount: 0,
      earnings: 0,
      hasUsedTrial: false,
    });

    return c.json({ success: true, user: data.user });
  } catch (err) {
    console.error('Signup error:', err);
    return c.json({ error: 'Internal server error during signup' }, 500);
  }
});

// Get user profile
app.get("/make-server-0ad4a249/profile", async (c) => {
  try {
    const accessToken = c.req.header('Authorization')?.split(' ')[1];
    if (!accessToken) {
      return c.json({ error: 'Unauthorized' }, 401);
    }

    const { data: { user }, error } = await supabase.auth.getUser(accessToken);
    if (error || !user) {
      return c.json({ error: 'Unauthorized' }, 401);
    }

    const userData = await kv.get(`user:${user.id}`);
    if (!userData) {
      return c.json({ error: 'User not found' }, 404);
    }

    return c.json({ user: userData });
  } catch (err) {
    console.error('Profile fetch error:', err);
    return c.json({ error: 'Internal server error while fetching profile' }, 500);
  }
});

// Update balance
app.post("/make-server-0ad4a249/balance/add", async (c) => {
  try {
    const accessToken = c.req.header('Authorization')?.split(' ')[1];
    if (!accessToken) {
      return c.json({ error: 'Unauthorized' }, 401);
    }

    const { data: { user }, error } = await supabase.auth.getUser(accessToken);
    if (error || !user) {
      return c.json({ error: 'Unauthorized' }, 401);
    }

    const body = await c.req.json();
    const { amount } = body;

    const userData = await kv.get(`user:${user.id}`);
    if (!userData) {
      return c.json({ error: 'User not found' }, 404);
    }

    userData.balance = (userData.balance || 0) + amount;
    await kv.set(`user:${user.id}`, userData);

    return c.json({ success: true, balance: userData.balance });
  } catch (err) {
    console.error('Balance update error:', err);
    return c.json({ error: 'Internal server error while updating balance' }, 500);
  }
});

// Get subscription
app.get("/make-server-0ad4a249/subscription", async (c) => {
  try {
    const accessToken = c.req.header('Authorization')?.split(' ')[1];
    if (!accessToken) {
      return c.json({ error: 'Unauthorized' }, 401);
    }

    const { data: { user }, error } = await supabase.auth.getUser(accessToken);
    if (error || !user) {
      return c.json({ error: 'Unauthorized' }, 401);
    }

    const subscription = await kv.get(`subscription:${user.id}`);
    return c.json({ subscription: subscription || null });
  } catch (err) {
    console.error('Subscription fetch error:', err);
    return c.json({ error: 'Internal server error while fetching subscription' }, 500);
  }
});

// Activate trial
app.post("/make-server-0ad4a249/subscription/trial", async (c) => {
  try {
    const accessToken = c.req.header('Authorization')?.split(' ')[1];
    if (!accessToken) {
      return c.json({ error: 'Unauthorized' }, 401);
    }

    const { data: { user }, error } = await supabase.auth.getUser(accessToken);
    if (error || !user) {
      return c.json({ error: 'Unauthorized' }, 401);
    }

    const userData = await kv.get(`user:${user.id}`);
    if (userData?.hasUsedTrial) {
      return c.json({ error: 'Trial already used' }, 400);
    }

    const endDate = new Date();
    endDate.setDate(endDate.getDate() + 7);

    await kv.set(`subscription:${user.id}`, {
      userId: user.id,
      isActive: true,
      startDate: new Date().toISOString(),
      endDate: endDate.toISOString(),
      isTrial: true,
    });

    userData.hasUsedTrial = true;
    await kv.set(`user:${user.id}`, userData);

    return c.json({ success: true });
  } catch (err) {
    console.error('Trial activation error:', err);
    return c.json({ error: 'Internal server error while activating trial' }, 500);
  }
});

// Get plans
app.get("/make-server-0ad4a249/plans", async (c) => {
  try {
    const plans = await kv.getByPrefix('plan:');
    
    // If no plans exist, create default ones
    if (!plans || plans.length === 0) {
      const defaultPlans = [
        {
          id: 'plan:1month',
          name: '1 месяц',
          price: 299,
          duration: 30,
          features: [
            'Безлимитный трафик',
            'Высокая скорость',
            'Серверы в 50+ странах',
            '24/7 поддержка',
          ],
          popular: false,
        },
        {
          id: 'plan:3months',
          name: '3 месяца',
          price: 699,
          duration: 90,
          features: [
            'Безлимитный трафик',
            'Высокая скорость',
            'Серверы в 50+ странах',
            '24/7 поддержка',
            'Скидка 22%',
          ],
          popular: true,
        },
        {
          id: 'plan:12months',
          name: '12 месяцев',
          price: 1999,
          duration: 365,
          features: [
            'Безлимитный трафик',
            'Максимальная скорость',
            'Серверы в 50+ странах',
            '24/7 приоритетная поддержка',
            'Скидка 44%',
          ],
          popular: false,
        },
      ];

      await kv.mset(defaultPlans.map(plan => [plan.id, plan]));
      return c.json({ plans: defaultPlans });
    }

    return c.json({ plans });
  } catch (err) {
    console.error('Plans fetch error:', err);
    return c.json({ error: 'Internal server error while fetching plans' }, 500);
  }
});

// Buy plan
app.post("/make-server-0ad4a249/plans/buy", async (c) => {
  try {
    const accessToken = c.req.header('Authorization')?.split(' ')[1];
    if (!accessToken) {
      return c.json({ error: 'Unauthorized' }, 401);
    }

    const { data: { user }, error } = await supabase.auth.getUser(accessToken);
    if (error || !user) {
      return c.json({ error: 'Unauthorized' }, 401);
    }

    const body = await c.req.json();
    const { planId } = body;

    const plan = await kv.get(planId);
    if (!plan) {
      return c.json({ error: 'Plan not found' }, 404);
    }

    const userData = await kv.get(`user:${user.id}`);
    if (!userData || userData.balance < plan.price) {
      return c.json({ error: 'Insufficient balance' }, 400);
    }

    userData.balance -= plan.price;
    await kv.set(`user:${user.id}`, userData);

    const endDate = new Date();
    endDate.setDate(endDate.getDate() + plan.duration);

    await kv.set(`subscription:${user.id}`, {
      userId: user.id,
      isActive: true,
      startDate: new Date().toISOString(),
      endDate: endDate.toISOString(),
      planId,
      isTrial: false,
    });

    return c.json({ success: true, balance: userData.balance });
  } catch (err) {
    console.error('Plan purchase error:', err);
    return c.json({ error: 'Internal server error while purchasing plan' }, 500);
  }
});

// Get referrals
app.get("/make-server-0ad4a249/referrals", async (c) => {
  try {
    const accessToken = c.req.header('Authorization')?.split(' ')[1];
    if (!accessToken) {
      return c.json({ error: 'Unauthorized' }, 401);
    }

    const { data: { user }, error } = await supabase.auth.getUser(accessToken);
    if (error || !user) {
      return c.json({ error: 'Unauthorized' }, 401);
    }

    const referrals = await kv.getByPrefix(`referral:${user.id}:`);
    return c.json({ referrals: referrals || [] });
  } catch (err) {
    console.error('Referrals fetch error:', err);
    return c.json({ error: 'Internal server error while fetching referrals' }, 500);
  }
});

// Withdraw referral earnings
app.post("/make-server-0ad4a249/referrals/withdraw", async (c) => {
  try {
    const accessToken = c.req.header('Authorization')?.split(' ')[1];
    if (!accessToken) {
      return c.json({ error: 'Unauthorized' }, 401);
    }

    const { data: { user }, error } = await supabase.auth.getUser(accessToken);
    if (error || !user) {
      return c.json({ error: 'Unauthorized' }, 401);
    }

    const userData = await kv.get(`user:${user.id}`);
    if (!userData || !userData.earnings || userData.earnings <= 0) {
      return c.json({ error: 'No earnings to withdraw' }, 400);
    }

    userData.balance = (userData.balance || 0) + userData.earnings;
    const withdrawn = userData.earnings;
    userData.earnings = 0;
    await kv.set(`user:${user.id}`, userData);

    return c.json({ success: true, withdrawn, balance: userData.balance });
  } catch (err) {
    console.error('Withdrawal error:', err);
    return c.json({ error: 'Internal server error during withdrawal' }, 500);
  }
});

Deno.serve(app.fetch);
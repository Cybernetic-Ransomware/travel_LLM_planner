// .claude/hooks/pre/secrets.ts – BLOKUJE zapis z secretami
import {readHookEvent, getFilePath} from '../index'

const SECRET_PATTERNS = [
    {regex: /['"]sk-[a-zA-Z0-9_-]{20,}['"]/, label: 'OpenAI API key'},
    {regex: /['"]ghp_[a-zA-Z0-9]{36,}['"]/, label: 'GitHub PAT'},
    {regex: /['"]AKIA[0-9A-Z]{16}['"]/, label: 'AWS access key'},
    {
        regex: /['"]mongodb\+srv:\/\/[^'"]+['"]/,
        label: 'MongoDB connection string'
    },
    {regex: /['"]redis:\/\/[^'"]+['"]/, label: 'Redis connection string'},
    {
        regex: /password\s*[=]\s*['"][^'"]{8,}['"]/,
        label: 'hardcoded password'
    }
]

function main(): void {
    const event = readHookEvent()
    const filePath = getFilePath(event)

    if (!filePath) {
        process.exit(0)
    }

    // Sprawdź treść, którą Claude Code chce zapisać
    const content =
        event.tool_input?.new_string ||
        event.tool_input?.content ||
        ''

    const matches = SECRET_PATTERNS.filter(p =>
        p.regex.test(content)
    )

    if (matches.length > 0) {
        const labels = matches
            .map(m => ` - ${m.label}`)
            .join('\n')

        console.error(
            `🚫 BLOCKED: Secrets detected in ${filePath}:\n${labels}`
        )
        console.error('Use environment variables instead.')

        process.exit(2) // exit code 2 = BLOKUJ operację
    }
}

main()
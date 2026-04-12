// .claude/hooks/post/console-log.ts
import {readFileSync} from 'fs'
import {readHookEvent, getFilePath} from '../index'

const CONSOLE_REGEX = /console\.(log|debug|info|warn|error)\(/
const ALLOWED_FILES = ['logger.ts', 'logging.ts']

function main(): void {
    const event = readHookEvent()
    const filePath = getFilePath(event)

    if (!filePath || !filePath.match(/\.(ts|tsx)$/)) {
        process.exit(0)
    }

    // Ignoruj pliki testowe i pliki loggera
    const fileName = filePath.split('/').pop() || ''

    if (ALLOWED_FILES.includes(fileName) || filePath.includes('.test.')) {
        process.exit(0)
    }

    const lines = readFileSync(filePath, 'utf-8').split('\n')

    const issues = lines
        .map((line, i) => ({line: i + 1, content: line.trim()}))
        .filter(l => CONSOLE_REGEX.test(l.content))

    if (issues.length > 0) {
        console.log(`⚠️ console.log found in ${fileName}:`)
        issues.forEach(i => {
            console.log(`  L${i.line}: ${i.content}`)
        })
        console.log('Use a proper logger instead.')

        // Brak process.exit(2) = ostrzeżenie, nie blokada
    }
}

main()